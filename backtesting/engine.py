"""
Backtesting Engine
==================
Runs strategy backtests using VectorBT for high-performance simulation.
"""

import logging
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
import vectorbt as vbt

from config.settings import COMMISSION, INITIAL_CAPITAL, SLIPPAGE

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Container for backtest results."""
    strategy_name: str
    ticker: str
    interval: str
    portfolio: vbt.Portfolio
    signals_df: pd.DataFrame
    initial_capital: float


class BacktestEngine:
    """Runs backtests on trading strategies using VectorBT."""

    def __init__(
        self,
        initial_capital: float = INITIAL_CAPITAL,
        commission: float = COMMISSION,
        slippage: float = SLIPPAGE,
    ):
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage

    def run(
        self,
        strategy,
        df: pd.DataFrame,
        ticker: str = '',
        interval: str = '',
        predictor=None,
        delay_sec: float = 0.0,
    ) -> BacktestResult:
        """Run a backtest for a given strategy on OHLCV+indicators data.

        Args:
            strategy: Strategy instance (must have generate_signals method).
            df: DataFrame with OHLCV + indicator columns.
            ticker: Ticker symbol for labeling.
            interval: Data interval for labeling.
            predictor: Optional XGBoostPredictor instance for ML filtering.
            delay_sec: Delay between ML predictions to avoid rate limits (if applicable).

        Returns:
            BacktestResult with portfolio and metrics.
        """
        logger.info(f"Running backtest: {strategy.name} on {ticker} ({interval})")
        if predictor:
            logger.info("ML Filter enabled for backtesting")

        # Generate base technical signals
        signals_df = strategy.generate_signals(df).copy()

        # Apply ML filter if predictor is provided
        if predictor:
            click_available = False
            try:
                import click
                click_available = True
            except ImportError:
                pass

            # We iterate through the technical signals and validate them with ML
            # This is slower than vectorbt but necessary for ML filtering
            technical_signals = signals_df[signals_df['signal'].isin(['BUY', 'SELL'])]
            
            if click_available:
                import click
                label = f"Filtering {len(technical_signals)} signals with ML"
                with click.progressbar(technical_signals.index, label=label) as bar:
                    for idx in bar:
                        self._process_ml_row(idx, signals_df, df, predictor, delay_sec)
            else:
                for idx in technical_signals.index:
                    self._process_ml_row(idx, signals_df, df, predictor, delay_sec)

        # Convert signals to boolean entry/exit arrays
        entries = signals_df['signal'] == 'BUY'
        exits = signals_df['signal'] == 'SELL'

        # Build portfolio with VectorBT
        portfolio = vbt.Portfolio.from_signals(
            close=signals_df['close'],
            entries=entries,
            exits=exits,
            init_cash=self.initial_capital,
            fees=self.commission,
            slippage=self.slippage,
            freq=self._interval_to_freq(interval),
        )

        result = BacktestResult(
            strategy_name=strategy.name,
            ticker=ticker,
            interval=interval,
            portfolio=portfolio,
            signals_df=signals_df,
            initial_capital=self.initial_capital,
        )

        logger.info(
            f"Backtest complete: {portfolio.stats()['Total Trades']} trades, "
            f"Return: {portfolio.stats()['Total Return [%]']:.2f}%"
        )
        return result

    def filter_by_date_range(
        self,
        result: BacktestResult,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> BacktestResult:
        """Restrict a completed backtest to a date range, re-running the portfolio.

        Applied AFTER run() so indicators/ML predictions still see the full
        history for warmup; only the resulting trade simulation is windowed.
        """
        if not start_date and not end_date:
            return result

        mask = pd.Series(True, index=result.signals_df.index)
        if start_date:
            mask &= (result.signals_df.index >= start_date)
        if end_date:
            mask &= (result.signals_df.index <= end_date)

        filtered_signals = result.signals_df[mask]
        result.portfolio = vbt.Portfolio.from_signals(
            close=filtered_signals['close'],
            entries=filtered_signals['signal'] == 'BUY',
            exits=filtered_signals['signal'] == 'SELL',
            init_cash=self.initial_capital,
            fees=self.commission,
            slippage=self.slippage,
            freq=self._interval_to_freq(result.interval),
        )
        result.signals_df = filtered_signals
        return result

    def _process_ml_row(self, idx, signals_df, df, predictor, delay_sec):
        """Internal helper to process a single signal row with ML."""
        # Get data slice up to current index for prediction
        df_slice = df.loc[:idx]
        
        # Ensure we have enough data for the predictor's lookback window
        lookback = getattr(predictor, 'lookback_window', 60)
        if len(df_slice) < lookback:
            logger.warning(f"Skipping ML filter for {idx}: Not enough history ({len(df_slice)} < {lookback})")
            return

        # Predict
        try:
            prediction = predictor.predict_next(df_slice)
            
            # Filter
            tech_signal = signals_df.loc[idx, 'signal']
            filter_result = predictor.filter_signal(tech_signal, prediction)
            
            if not filter_result['accepted']:
                logger.info(f"ML filter REJECTED {tech_signal} at {idx}: {filter_result['reason']}")
                signals_df.at[idx, 'signal'] = 'HOLD'
                signals_df.at[idx, 'confidence'] = 0.0
        except Exception as e:
            logger.error(f"Error in ML prediction at {idx}: {e}")
            
        if delay_sec > 0:
            time.sleep(delay_sec)

    @staticmethod
    def _interval_to_freq(interval: str) -> str | None:
        """Convert interval string to pandas frequency."""
        freq_map = {
            '1m': '1min',
            '5m': '5min',
            '15m': '15min',
            '1h': '1h',
            '1d': '1D',
        }
        return freq_map.get(interval)
