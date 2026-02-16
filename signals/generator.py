"""
Signal Generator Module
========================
Generates trading signals by fetching fresh data, computing indicators,
and applying a strategy.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from config.settings import SIGNAL_LOOKBACK_BARS, SIGNAL_CONFIDENCE_HIGH
from data.fetcher import DataFetcher
from data.processor import DataProcessor
from indicators.technical import TechnicalIndicators
from strategies import STRATEGY_MAP

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """Represents a single trading signal."""
    strategy: str
    ticker: str
    interval: str
    direction: str          # BUY, SELL, HOLD
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float
    timestamp: datetime = field(default_factory=datetime.now)
    ml_filtered: bool = False
    ml_confidence: float | None = None
    ensemble_consensus: str | None = None        # STRONG, WEAK, None
    news_sentiment: dict | None = None           # {sentiment, confidence, headline}
    confluence_score: int = 0                    # 0-5 stars

    @property
    def risk_reward_ratio(self) -> float | None:
        """Calculate risk/reward ratio."""
        if self.direction == 'HOLD' or self.stop_loss == 0 or self.take_profit == 0:
            return None
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.take_profit - self.entry_price)
        if risk == 0:
            return None
        return round(reward / risk, 2)

    def to_dict(self) -> dict[str, Any]:
        """Convert signal to dictionary."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'strategy': self.strategy,
            'ticker': self.ticker,
            'interval': self.interval,
            'direction': self.direction,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'confidence': self.confidence,
            'risk_reward': self.risk_reward_ratio or '',
            'ml_filtered': self.ml_filtered,
            'ml_confidence': self.ml_confidence if self.ml_confidence is not None else '',
            'ensemble_consensus': self.ensemble_consensus or '',
            'news_sentiment': self.news_sentiment.get('sentiment', {}).get('sentiment', '') if self.news_sentiment else '',
            'confluence_score': self.confluence_score,
        }


class SignalGenerator:
    """Generates trading signals from fresh market data."""

    def __init__(self):
        self.fetcher = DataFetcher()
        self.processor = DataProcessor()

    def generate(
        self,
        strategy_name: str,
        ticker: str,
        interval: str = '1d',
        days: int | None = None,
        use_ml: bool = False,
    ) -> Signal:
        """Generate a signal for a given strategy and ticker.

        Fetches fresh data, computes indicators, applies strategy,
        and returns the latest signal.

        Args:
            strategy_name: Key from STRATEGY_MAP (e.g. 'macd_vwap').
            ticker: Ticker symbol.
            interval: Data interval.
            days: Days of history to fetch. Auto-calculated if None.
            use_ml: Whether to filter with ML model.

        Returns:
            Signal object with the latest trading signal.
        """
        if strategy_name not in STRATEGY_MAP:
            raise ValueError(f"Unknown strategy: {strategy_name}. Available: {list(STRATEGY_MAP.keys())}")

        # Auto-calculate days based on interval for sufficient indicator warmup
        if days is None:
            days = self._estimate_days(interval)

        # 1. Fetch fresh data
        logger.info(f"Fetching {ticker} {interval} data ({days}d) for signal generation")
        df = self.fetcher.fetch_yfinance(ticker, interval, days)
        df = self.processor.clean_data(df)
        self.processor.validate_data(df)

        # 2. Compute indicators
        df = TechnicalIndicators.add_all_indicators(df)

        # 3. Apply strategy
        strategy = STRATEGY_MAP[strategy_name]()
        signals_df = strategy.generate_signals(df)

        # 4. Extract the latest signal
        latest = signals_df.iloc[-1]
        signal = Signal(
            strategy=strategy_name,
            ticker=ticker,
            interval=interval,
            direction=latest['signal'],
            entry_price=float(latest['close']),
            stop_loss=float(latest['stop_loss']),
            take_profit=float(latest['take_profit']),
            confidence=float(latest['confidence']),
        )

        # 5. ML filter (Phase 6)
        if use_ml:
            signal = self._apply_ml_filter(signal, df)

        logger.info(f"Signal generated: {signal.direction} {ticker} @ {signal.entry_price:.2f} (conf: {signal.confidence:.2f})")
        return signal

    def get_latest_actionable(
        self,
        strategy_name: str,
        ticker: str,
        interval: str = '1d',
        days: int | None = None,
        lookback: int = 5,
    ) -> Signal | None:
        """Get the most recent BUY or SELL signal within the last N bars.

        Args:
            strategy_name: Key from STRATEGY_MAP.
            ticker: Ticker symbol.
            interval: Data interval.
            days: Days of history.
            lookback: How many recent bars to search for a signal.

        Returns:
            Signal if a BUY/SELL was found recently, None otherwise.
        """
        if strategy_name not in STRATEGY_MAP:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        if days is None:
            days = self._estimate_days(interval)

        df = self.fetcher.fetch_yfinance(ticker, interval, days)
        df = self.processor.clean_data(df)
        self.processor.validate_data(df)
        df = TechnicalIndicators.add_all_indicators(df)

        strategy = STRATEGY_MAP[strategy_name]()
        signals_df = strategy.generate_signals(df)

        # Search last N bars for an actionable signal
        recent = signals_df.tail(lookback)
        actionable = recent[recent['signal'].isin(['BUY', 'SELL'])]

        if actionable.empty:
            return None

        last = actionable.iloc[-1]
        return Signal(
            strategy=strategy_name,
            ticker=ticker,
            interval=interval,
            direction=last['signal'],
            entry_price=float(last['close']),
            stop_loss=float(last['stop_loss']),
            take_profit=float(last['take_profit']),
            confidence=float(last['confidence']),
            timestamp=last.name.to_pydatetime() if hasattr(last.name, 'to_pydatetime') else datetime.now(),
        )

    def _apply_ml_filter(self, signal: Signal, df: pd.DataFrame) -> Signal:
        """Apply ML model prediction as a filter on the signal.

        Uses lower thresholds to combine technical signals with ML predictions:
        - If technical signal is strong (BUY/SELL), keep it if ML doesn't strongly disagree
        - If technical signal is HOLD but ML has high confidence (>55%), use ML signal
        - If both signals agree, boost confidence

        If ML model is not available, returns the signal unchanged with a warning.
        """
        try:
            from models.predictor import PricePredictor
            predictor = PricePredictor(confidence_threshold=0.55)  # Lower threshold for combining
            predictor.load(signal.ticker, signal.interval)
            prediction = predictor.predict_next(df)

            signal.ml_filtered = True
            signal.ml_confidence = prediction.get('confidence', 0)
            ml_direction = prediction['direction']
            ml_confidence = prediction['confidence']

            # Combine signals with lower thresholds
            if signal.direction == 'HOLD':
                # Technical signal is HOLD: use ML signal if it has high confidence (>55%)
                if ml_confidence > 0.55:
                    logger.info(f"ML overrides HOLD with {ml_direction} ({ml_confidence:.1%} confidence)")
                    signal.direction = ml_direction
                    signal.confidence = ml_confidence
            elif signal.direction == ml_direction:
                # Both signals agree: boost confidence
                combined_confidence = min(1.0, (signal.confidence + ml_confidence) / 2)
                logger.info(f"ML confirms {signal.direction} - combined confidence: {combined_confidence:.2f}")
                signal.confidence = combined_confidence
            else:
                # Signals disagree: only reject if ML has high opposing confidence (>65%)
                if ml_confidence > 0.65:
                    logger.info(f"ML strongly disagrees ({ml_direction} {ml_confidence:.1%}). Rejecting signal.")
                    signal.direction = 'HOLD'
                    signal.confidence = 0.0
                else:
                    # Keep technical signal if ML opposition is weak (<65%)
                    logger.info(f"ML weakly disagrees ({ml_direction} {ml_confidence:.1%}). Keeping technical signal.")

        except (ImportError, FileNotFoundError) as e:
            logger.warning(f"ML model not available ({e}). Signal passed without ML filter.")

        return signal

    @staticmethod
    def _estimate_days(interval: str) -> int:
        """Estimate how many days of data to fetch for sufficient indicator warmup."""
        days_map = {
            '1m': 7,       # 7 days of minute data (~2700 bars)
            '5m': 30,      # 30 days (~1700 bars)
            '15m': 55,     # 55 days (~1400 bars) - Yahoo limit is 60d, use 55 for safety
            '1h': 90,      # 90 days (~1500 bars)
            '1d': 365,     # 1 year (~250 bars, enough for SMA200)
        }
        return days_map.get(interval, 365)
