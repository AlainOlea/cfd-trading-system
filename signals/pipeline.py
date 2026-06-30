"""
Unified Signal Pipeline
========================
Consolidates all signal generation flows (technical, ML, ensemble, news)
into a single configurable pipeline.

Usage:
    from signals.pipeline import UnifiedPipeline, TickerConfig

    pipeline = UnifiedPipeline()
    results = pipeline.run_all()  # Uses PIPELINE_TICKERS from settings

    # Or for a single ticker:
    config = TickerConfig('SPY', 'indices', ['1d', '1h'], ['macd_vwap', 'rsi_bb'])
    results = pipeline.run_ticker(config)
"""

import logging
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from config.settings import (
    MARKET_HOURS, TICKERS as TICKER_GROUPS, PIPELINE_TICKERS_RAW,
    TELEGRAM_HEALTH_CHECK_ENABLED,
    SCALPING_SL_PERCENT, SCALPING_TP_PERCENT,
    SWING_SL_PERCENT, SWING_TP_PERCENT,
)
from data.fetcher import DataFetcher
from data.processor import DataProcessor
from indicators.technical import TechnicalIndicators
from signals.generator import Signal, SignalGenerator
from strategies import STRATEGY_MAP
from signals.manager import SignalManager
from signals.telegram_bot import TelegramNotifier

logger = logging.getLogger(__name__)


def _build_pipeline_tickers() -> list['TickerConfig']:
    """Build TickerConfig list from raw tuples in settings.py."""
    return [
        TickerConfig(
            ticker=t[0], category=t[1], intervals=t[2], strategies=t[3],
            use_ml=t[4], use_ensemble=t[5], use_news=t[6],
            confluence_min_stars=t[7],
        )
        for t in PIPELINE_TICKERS_RAW
    ]


@dataclass
class TickerConfig:
    """Configuration per ticker for the pipeline."""
    ticker: str
    category: str                   # indices, stocks, crypto, commodities
    intervals: list[str]            # ['1d', '1h', '15m']
    strategies: list[str]           # ['macd_vwap', 'rsi_bb']
    use_ml: bool = True
    use_ensemble: bool = True
    use_news: bool = True
    confluence_min_stars: int = 2   # minimum to consider actionable


@dataclass
class PipelineResult:
    """Complete result from the pipeline for one ticker+interval."""
    ticker: str
    interval: str
    technical_signal: Signal
    ml_prediction: dict | None = None
    ensemble_result: dict | None = None
    news_sentiment: dict | None = None
    confluence_score: int = 0           # 0-5 stars
    confluence_min_stars: int = 2       # minimum to be actionable
    final_direction: str = 'HOLD'       # BUY/SELL/HOLD
    final_confidence: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def is_actionable(self) -> bool:
        """Check if this result has an actionable signal."""
        return (
            self.final_direction in ('BUY', 'SELL')
            and self.confluence_score >= self.confluence_min_stars
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'ticker': self.ticker,
            'interval': self.interval,
            'technical_direction': self.technical_signal.direction,
            'technical_confidence': self.technical_signal.confidence,
            'ml_direction': self.ml_prediction.get('direction') if self.ml_prediction else '',
            'ml_confidence': self.ml_prediction.get('confidence') if self.ml_prediction else '',
            'ensemble_consensus': self.ensemble_result.get('consensus') if self.ensemble_result else '',
            'ensemble_confidence': self.ensemble_result.get('confidence') if self.ensemble_result else '',
            'news_sentiment': self.news_sentiment.get('sentiment', {}).get('sentiment') if self.news_sentiment else '',
            'news_alignment': self.news_sentiment.get('sentiment', {}).get('alignment') if self.news_sentiment else '',
            'confluence_score': self.confluence_score,
            'final_direction': self.final_direction,
            'final_confidence': self.final_confidence,
        }


class UnifiedPipeline:
    """Unified signal generation pipeline.

    Consolidates technical analysis, ML prediction, ensemble voting,
    and news sentiment into a single flow.
    """

    def __init__(
        self,
        use_ml: bool = True,
        use_ensemble: bool = True,
        use_news: bool = True,
        send_telegram: bool = True,
        max_workers: int = 4,
    ):
        self.use_ml = use_ml
        self.use_ensemble = use_ensemble
        self.use_news = use_news
        self.send_telegram = send_telegram
        self._dedup_file = Path('logs/.telegram_dedup')
        self.max_workers = max_workers
        self._fetch_lock = threading.Lock()
        self._data_freshness: dict[str, str] = {}  # ticker_interval -> status
        self.fetcher = DataFetcher()
        self.processor = DataProcessor()
        self.generator = SignalGenerator()
        self.manager = SignalManager()
        self.notifier = TelegramNotifier()
        self._tfm_results: dict = {}
        # Shared data cache — populated by _fetch_data() during run_all(), cleared at
        # start of each run. Lets TimesFM reuse data already fetched by the pipeline
        # instead of making a separate API call.
        self._run_cache: dict[str, pd.DataFrame] = {}
        try:
            from models.timesfm_predictor import TimesFMPredictor
            self.timesfm = TimesFMPredictor()
        except ImportError:
            self.timesfm = None
            logger.debug("TimesFM not available (timesfm package not installed)")

    def run_ticker(self, config: TickerConfig) -> list[PipelineResult]:
        """Execute the full pipeline for a single ticker across all its intervals.

        Args:
            config: TickerConfig with ticker settings.

        Returns:
            List of PipelineResult, one per interval.
        """
        results = []
        data_cache: dict[str, pd.DataFrame] = {}

        for interval in config.intervals:
            try:
                result = self._run_single(config, interval, data_cache)
                results.append(result)
            except Exception as e:
                logger.error(f"Pipeline error for {config.ticker} {interval}: {e}\n{traceback.format_exc()}")

        # Compute multi-timeframe confluence across all intervals
        if results:
            confluence = self._compute_confluence(results)
            for r in results:
                r.confluence_score = confluence

        return results

    def run_all(
        self,
        configs: list[TickerConfig] | None = None,
        category: str | None = None,
        ticker_filter: str | None = None,
        interval_filter: str | None = None,
    ) -> list[PipelineResult]:
        """Execute pipeline for all configured tickers.

        Args:
            configs: List of TickerConfig. If None, uses PIPELINE_TICKERS from settings.
            category: Filter by category ('indices', 'stocks', 'crypto', 'commodities').
            ticker_filter: Run for a specific ticker only.
            interval_filter: Restrict to a single interval ('1d' or '1h'). If None, uses
                all intervals configured per ticker.

        Returns:
            List of all PipelineResult objects.
        """
        if configs is None:
            configs = _build_pipeline_tickers()

        # Apply filters
        if category and category != 'all':
            configs = [c for c in configs if c.category == category]
        if ticker_filter:
            configs = [c for c in configs if c.ticker == ticker_filter]
        if interval_filter:
            configs = [
                TickerConfig(
                    ticker=c.ticker, category=c.category,
                    intervals=[interval_filter],
                    strategies=c.strategies, use_ml=c.use_ml,
                    use_ensemble=c.use_ensemble, use_news=c.use_news,
                    confluence_min_stars=c.confluence_min_stars,
                )
                for c in configs if interval_filter in c.intervals
            ]

        # Reset per-run data cache. _fetch_data() populates this so the same
        # ticker+interval is never fetched twice within a single run_all() call.
        self._run_cache = {}

        all_results: list[PipelineResult] = []

        # Run tickers in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_config = {
                executor.submit(self.run_ticker, config): config
                for config in configs
            }
            for future in as_completed(future_to_config):
                config = future_to_config[future]
                try:
                    results = future.result()
                    all_results.extend(results)
                except Exception as e:
                    logger.error(f"Pipeline failed for {config.ticker}: {e}\n{traceback.format_exc()}")

        # Run TimesFM AFTER the main pipeline so it reuses _run_cache (no extra fetches).
        # Then apply confluence bonus and dynamic SL/TP to the collected results.
        self._run_timesfm_batch(configs)
        self._apply_timesfm(all_results)

        return all_results

    def _run_single(
        self,
        config: TickerConfig,
        interval: str,
        data_cache: dict[str, pd.DataFrame],
    ) -> PipelineResult:
        """Run pipeline for one ticker + one interval.

        Args:
            config: Ticker configuration.
            interval: Data interval (e.g. '1d', '1h').
            data_cache: Shared cache to avoid re-fetching data.

        Returns:
            PipelineResult with all analysis layers.
        """
        # 1. Fetch and prepare data (reuse from cache if available)
        cache_key = f"{config.ticker}_{interval}"
        if cache_key not in data_cache:
            df = self._fetch_data(config.ticker, interval)
            data_cache[cache_key] = df
        df = data_cache[cache_key]

        # 2. Apply strategies and search last N bars for actionable signals
        lookback = 5
        best_signal = None
        for strategy_name in config.strategies:
            try:
                if strategy_name not in STRATEGY_MAP:
                    logger.warning(f"Unknown strategy: {strategy_name}")
                    continue

                strategy = STRATEGY_MAP[strategy_name]()
                signals_df = strategy.generate_signals(df.copy())

                # Search last N bars for a BUY/SELL signal with valid SL/TP
                recent = signals_df.tail(lookback)
                actionable = recent[recent['signal'].isin(['BUY', 'SELL'])]

                if not actionable.empty:
                    last = actionable.iloc[-1]
                    signal = Signal(
                        strategy=strategy_name,
                        ticker=config.ticker,
                        interval=interval,
                        direction=last['signal'],
                        entry_price=float(last['close']),
                        stop_loss=float(last['stop_loss']),
                        take_profit=float(last['take_profit']),
                        confidence=float(last['confidence']),
                    )
                else:
                    last_row = signals_df.iloc[-1]
                    signal = Signal(
                        strategy=strategy_name,
                        ticker=config.ticker,
                        interval=interval,
                        direction='HOLD',
                        entry_price=float(last_row['close']),
                        stop_loss=0.0,
                        take_profit=0.0,
                        confidence=0.0,
                    )

                # Pick the most actionable signal (BUY/SELL over HOLD, highest confidence)
                if best_signal is None:
                    best_signal = signal
                elif signal.direction != 'HOLD' and (
                    best_signal.direction == 'HOLD' or signal.confidence > best_signal.confidence
                ):
                    best_signal = signal

                # Dedup: once we have an actionable signal, skip remaining strategies
                # to avoid double-firing (e.g. MACD+VWAP and RSI+BB on same condition)
                if best_signal.direction != 'HOLD':
                    break
            except Exception as e:
                logger.warning(f"Strategy {strategy_name} failed for {config.ticker} {interval}: {e}")

        if best_signal is None:
            raise RuntimeError(f"All strategies failed for {config.ticker} {interval}")

        result = PipelineResult(
            ticker=config.ticker,
            interval=interval,
            technical_signal=best_signal,
            final_direction=best_signal.direction,
            final_confidence=best_signal.confidence,
            confluence_min_stars=config.confluence_min_stars,
        )

        # 3. ML filter (single model)
        if self.use_ml and config.use_ml:
            result.ml_prediction = self._apply_ml(config.ticker, interval, df)

        # 4. Ensemble prediction (LSTM + XGBoost)
        if self.use_ensemble and config.use_ensemble:
            result.ensemble_result = self._apply_ensemble(config.ticker, interval, df)

        # 5. Compute final direction from all layers
        self._compute_final_signal(result)

        # 6. News sentiment (only for actionable signals to save API calls)
        if self.use_news and config.use_news and result.final_direction != 'HOLD':
            result.news_sentiment = self._apply_news(config.ticker, result)

        # 7. Update Signal dataclass with pipeline enrichments
        best_signal.ensemble_consensus = (
            result.ensemble_result.get('consensus') if result.ensemble_result else None
        )
        best_signal.news_sentiment = result.news_sentiment
        best_signal.confluence_score = result.confluence_score

        return result

    def _fetch_data(self, ticker: str, interval: str) -> pd.DataFrame:
        """Fetch FRESH data for a ticker+interval.

        Default: incremental fetch from Alpaca Data API (only new candles).
        Fallback: Yahoo Finance if Alpaca is unavailable.

        Thread-safe: serializes fetch calls with a lock.
        Saves to CSV as backup after fetching.
        Results are cached in self._run_cache for the duration of run_all() so the
        same ticker+interval is never fetched twice in a single pipeline invocation.
        """
        cache_key = f"{ticker}_{interval}"
        if cache_key in self._run_cache:
            return self._run_cache[cache_key]

        used_fallback = False

        with self._fetch_lock:
            # Re-check inside lock: another thread may have fetched while we waited
            if cache_key in self._run_cache:
                return self._run_cache[cache_key]
            try:
                # Try incremental fetch (Alpaca Data API)
                from data.alpaca_data import ALPACA_DATA_AVAILABLE
                if ALPACA_DATA_AVAILABLE:
                    logger.info(f"Incremental fetch for {ticker} {interval}")
                    df = self.fetcher.fetch_incremental(ticker, interval)
                else:
                    raise ImportError("Alpaca Data API not available")
            except Exception:
                # Fallback to Yahoo Finance
                used_fallback = True
                days = self.generator._estimate_days(interval)
                logger.info(f"Yahoo Finance fallback for {ticker} {interval} ({days}d)")
                df = self.fetcher.fetch_yfinance(ticker, interval, days)

        df = self.processor.clean_data(df)
        self.processor.validate_data(df)
        self.fetcher.save_to_csv(df, ticker, interval)
        df = TechnicalIndicators.add_all_indicators(df)

        # Track data freshness for health check
        try:
            last_ts = df.index[-1]
            # Normalize to naive UTC for comparison
            if hasattr(last_ts, 'tz') and last_ts.tz is not None:
                last_ts = last_ts.tz_localize(None)
            now_utc = datetime.utcnow()
            staleness_hours = (now_utc - last_ts).total_seconds() / 3600
            if used_fallback:
                self._data_freshness[cache_key] = f"yfinance ({staleness_hours:.0f}h stale)"
            elif staleness_hours > 24:
                self._data_freshness[cache_key] = f"Alpaca ({staleness_hours:.0f}h stale)"
            else:
                self._data_freshness[cache_key] = f"fresh ({staleness_hours:.1f}h)"
        except Exception:
            self._data_freshness[cache_key] = "unknown"

        self._run_cache[cache_key] = df
        return df

    def _run_timesfm_batch(self, configs: list[TickerConfig]) -> None:
        """Run TimesFM batch forecast using 1min data already in the run cache.

        Results stored in self._tfm_results = {ticker: result_dict}.
        Must be called AFTER the main pipeline run so that _run_cache is populated.

        Data priority for each ticker:
          1. _run_cache['ticker_1m']  — fetched this run (zero extra API calls)
          2. CSV on disk              — from last run (no API call, may be ~1h stale)
          3. Skip ticker              — no data available
        """
        self._tfm_results = {}
        if self.timesfm is None:
            return

        unique_tickers = list({cfg.ticker for cfg in configs})
        prices_1min: dict[str, object] = {}
        for ticker in unique_tickers:
            df = None
            cache_key = f"{ticker}_1m"
            if cache_key in self._run_cache:
                df = self._run_cache[cache_key]
            else:
                try:
                    df = self.fetcher.load_from_csv(ticker, '1m')
                    df = TechnicalIndicators.add_all_indicators(df)
                except FileNotFoundError:
                    logger.debug("TimesFM: no 1min data for %s (no cache, no CSV)", ticker)
                except Exception as e:
                    logger.debug("TimesFM: CSV load failed for %s: %s", ticker, e)

            if df is not None and len(df) >= 512:
                prices_1min[ticker] = df['close'].values

        if not prices_1min:
            logger.debug("TimesFM: no 1min data available for any ticker")
            return

        logger.info("TimesFM batch forecast for %d tickers", len(prices_1min))
        try:
            self._tfm_results = self.timesfm.predict_batch(prices_1min, horizon=60)
            logger.info("TimesFM ready — %d forecasts", len(self._tfm_results))
        except Exception as e:
            logger.warning("TimesFM batch forecast failed: %s", e)
            self._tfm_results = {}

    def _apply_timesfm(self, results: list['PipelineResult']) -> None:
        """Apply TimesFM results to already-computed pipeline results.

        Called as post-processing in run_all() after _run_timesfm_batch().
        Two effects for 1m/1h signals only (1d: directional accuracy ~44%, not used):
          - Confluence bonus: +1 star if TimesFM direction matches technical signal
          - Dynamic SL/TP: overwrite fixed-% levels with quantile-based prices
        """
        if not self._tfm_results:
            return

        for r in results:
            if r.interval not in ('1m', '1h') or r.final_direction == 'HOLD':
                continue
            tfm = self._tfm_results.get(r.ticker)
            if tfm is None:
                continue

            tech_dir = +1 if r.final_direction == 'BUY' else -1

            # Confluence bonus
            if tfm['direction'] == tech_dir and r.confluence_score < 5:
                r.confluence_score += 1
                logger.debug(
                    "TimesFM +1 confluence for %s %s → %d stars",
                    r.ticker, r.interval, r.confluence_score,
                )

            # Dynamic SL/TP — direction-aware quantile selection.
            # BUY:  SL = 10th pct at t=1 (below entry), TP = 80th pct at t=end (above entry)
            # SELL: SL = 80th pct at t=1 (above entry), TP = 10th pct at t=end (below entry)
            # Fallback to fixed % if quantiles are invalid or missing.
            quantiles = tfm.get('quantiles')
            entry = r.technical_signal.entry_price
            sl_pct = SCALPING_SL_PERCENT if r.interval in ('1m', '1h') else SWING_SL_PERCENT
            tp_pct = SCALPING_TP_PERCENT if r.interval in ('1m', '1h') else SWING_TP_PERCENT
            if r.final_direction == 'BUY':
                fallback_sl = entry * (1 - sl_pct)
                fallback_tp = entry * (1 + tp_pct)
            else:
                fallback_sl = entry * (1 + sl_pct)
                fallback_tp = entry * (1 - tp_pct)

            sl, tp = fallback_sl, fallback_tp  # default to fixed %
            if quantiles is not None and entry > 0:
                if r.final_direction == 'BUY':
                    q_sl = float(quantiles[0, 1])   # 10th pct at t=1
                    q_tp = float(quantiles[-1, 8])  # 80th pct at t=end
                    if q_sl < entry < q_tp:
                        sl, tp = q_sl, q_tp
                else:  # SELL
                    q_sl = float(quantiles[0, 8])   # 80th pct at t=1
                    q_tp = float(quantiles[-1, 1])  # 10th pct at t=end
                    if q_tp < entry < q_sl:
                        sl, tp = q_sl, q_tp

            r.technical_signal.stop_loss = sl
            r.technical_signal.take_profit = tp
            logger.debug(
                "TimesFM SL/TP for %s %s %s: SL=%.4f TP=%.4f",
                r.ticker, r.interval, r.final_direction, sl, tp,
            )

    def _apply_ml(self, ticker: str, interval: str, df: pd.DataFrame) -> dict | None:
        """Apply ML prediction (prefers cross-sectional XGBoost, falls back to per-ticker)."""
        try:
            from config.settings import PRIMARY_ML_MODEL
            if PRIMARY_ML_MODEL == 'xgboost':
                from models.xgboost_model import XGBoostPredictor
                predictor = XGBoostPredictor(confidence_threshold=0.55)
                # Try cross-sectional model first, then per-ticker
                for model_name in ['all_tickers', ticker]:
                    try:
                        predictor.load(model_name, interval)
                        return predictor.predict_next(df)
                    except FileNotFoundError:
                        continue
                logger.debug(f"XGBoost not available for {ticker} {interval}")
                return None
            else:
                from models.predictor import PricePredictor
                predictor = PricePredictor(confidence_threshold=0.55, allow_unpromoted=True)
                predictor.load(ticker, interval)
                return predictor.predict_next(df)
        except (ImportError, FileNotFoundError, Exception) as e:
            logger.debug(f"ML not available for {ticker} {interval}: {e}")
            return None

    def _apply_ensemble(self, ticker: str, interval: str, df: pd.DataFrame) -> dict | None:
        """Apply ensemble (LSTM + XGBoost) prediction."""
        try:
            from models.ensemble_predictor import EnsemblePredictor
            ensemble = EnsemblePredictor(lstm_threshold=0.65, xgb_threshold=0.65)
            ensemble.load(ticker, interval, models=['lstm', 'xgb'])
            pred = ensemble.predict_next(df)
            return pred.get('ensemble')
        except (ImportError, FileNotFoundError, Exception) as e:
            logger.debug(f"Ensemble not available for {ticker} {interval}: {e}")
            return None

    def _apply_news(self, ticker: str, result: PipelineResult) -> dict | None:
        """Fetch and analyze news sentiment."""
        try:
            from signals.news_analyzer import NewsAnalyzer
            analyzer = NewsAnalyzer()
            signal_dict = {
                'direction': result.final_direction,
                'confidence': result.final_confidence,
            }
            return analyzer.get_signal_context(ticker, signal_dict)
        except (ImportError, Exception) as e:
            logger.debug(f"News not available for {ticker}: {e}")
            return None

    def _compute_final_signal(self, result: PipelineResult) -> None:
        """Compute final direction and confidence from all analysis layers.

        Combines technical signal, ML prediction, and ensemble voting.
        Updates result.final_direction and result.final_confidence in place.
        """
        tech_dir = result.technical_signal.direction
        tech_conf = result.technical_signal.confidence

        # Start with technical signal
        final_dir = tech_dir
        final_conf = tech_conf
        votes_buy = 0
        votes_sell = 0
        total_votes = 0

        # Count technical vote
        if tech_dir == 'BUY':
            votes_buy += 1
        elif tech_dir == 'SELL':
            votes_sell += 1
        total_votes += 1

        # ML vote
        if result.ml_prediction:
            ml_dir = result.ml_prediction.get('direction', 'HOLD')
            ml_conf = result.ml_prediction.get('confidence', 0)
            if ml_dir == 'BUY':
                votes_buy += 1
            elif ml_dir == 'SELL':
                votes_sell += 1
            total_votes += 1

            # If ML strongly disagrees (>65%), downgrade
            if ml_dir != tech_dir and ml_conf > 0.65 and tech_dir != 'HOLD':
                final_dir = 'HOLD'
                final_conf = 0.0

        # Ensemble vote
        if result.ensemble_result:
            ens_dir = result.ensemble_result.get('direction', 'HOLD')
            ens_consensus = result.ensemble_result.get('consensus', 'WEAK')
            ens_conf = result.ensemble_result.get('confidence', 0)

            if ens_dir == 'BUY':
                votes_buy += 1
            elif ens_dir == 'SELL':
                votes_sell += 1
            total_votes += 1

            # Strong ensemble agreement boosts confidence
            if ens_consensus == 'STRONG' and ens_dir == tech_dir:
                final_conf = min(1.0, (tech_conf + ens_conf) / 2 + 0.05)
            # Strong ensemble disagreement forces HOLD
            elif ens_consensus == 'STRONG' and ens_dir != tech_dir and tech_dir != 'HOLD':
                final_dir = 'HOLD'
                final_conf = 0.0

        # If technical was HOLD but ML/ensemble agree on direction, upgrade
        if tech_dir == 'HOLD' and total_votes >= 2:
            if votes_buy >= 2 and result.ml_prediction and result.ml_prediction.get('confidence', 0) > 0.6:
                final_dir = 'BUY'
                final_conf = result.ml_prediction['confidence']
            elif votes_sell >= 2 and result.ml_prediction and result.ml_prediction.get('confidence', 0) > 0.6:
                final_dir = 'SELL'
                final_conf = result.ml_prediction['confidence']

        result.final_direction = final_dir
        result.final_confidence = final_conf

    def _compute_confluence(self, results: list[PipelineResult]) -> int:
        """Compute multi-timeframe confluence score (0-5 stars).

        Stars:
        1. At least one actionable signal (base)
        2. Multiple timeframes agree OR ML confirms the direction
        3. Both ML confirms AND (multi-TF agree OR ML confidence >65%)
        4. Ensemble has STRONG consensus
        5. High confidence across all layers (avg >= 70%)

        Stars are additive: a signal with ML confirmation and multi-TF
        agreement but no ensemble gets 3 stars.
        """
        if not results:
            return 0

        stars = 0
        directions = [r.final_direction for r in results if r.final_direction != 'HOLD']

        if not directions:
            return 0

        # Star 1: At least one actionable signal
        stars += 1

        # Star 2: Multiple timeframes agree OR ML confirms
        multi_tf = len(directions) >= 2 and len(set(directions)) == 1
        ml_confirms = any(
            r.ml_prediction and r.ml_prediction.get('direction') == r.final_direction
            for r in results if r.final_direction != 'HOLD'
        )
        if multi_tf or ml_confirms:
            stars += 1

        # Star 3: ML confirms AND (multi-TF or strong ML conviction >65%)
        ml_strong = any(
            r.ml_prediction
            and r.ml_prediction.get('direction') == r.final_direction
            and r.ml_prediction.get('confidence', 0) > 0.65
            for r in results if r.final_direction != 'HOLD'
        )
        if ml_confirms and (multi_tf or ml_strong):
            stars += 1

        # Star 4: Ensemble STRONG consensus (any interval)
        ensemble_strong = any(
            r.ensemble_result and r.ensemble_result.get('consensus') == 'STRONG'
            and r.ensemble_result.get('direction') == r.final_direction
            for r in results if r.final_direction != 'HOLD'
        )
        if ensemble_strong:
            stars += 1

        # Star 5: High average confidence (>70%)
        actionable = [r for r in results if r.final_direction != 'HOLD']
        if actionable:
            avg_conf = sum(r.final_confidence for r in actionable) / len(actionable)
            if avg_conf >= 0.70:
                stars += 1

        return min(stars, 5)

    # ─── Output formatting ───────────────────────────────────────

    def format_result(self, result: PipelineResult) -> str:
        """Format a single PipelineResult for terminal display."""
        stars = '*' * result.confluence_score + '.' * (5 - result.confluence_score)

        if result.final_direction == 'HOLD':
            return (
                f"  {result.ticker:8s} {result.interval:4s} | HOLD "
                f"| Confluence: [{stars}]"
            )

        lines = [
            "",
            "=" * 65,
            f"  {result.final_direction} {result.ticker} ({result.interval})",
            f"  Confluence: [{stars}] ({result.confluence_score}/5)",
            "-" * 65,
            f"  Entry:      ${result.technical_signal.entry_price:>12,.2f}",
            f"  Stop Loss:  ${result.technical_signal.stop_loss:>12,.2f}",
            f"  Take Profit:${result.technical_signal.take_profit:>12,.2f}",
        ]

        rr = result.technical_signal.risk_reward_ratio
        if rr:
            lines.append(f"  Risk/Reward: {'1:' + f'{rr:.1f}':>11}")

        lines.append(f"  Confidence:  {result.final_confidence:>12.1%}")
        lines.append("-" * 65)

        # Layers
        layers = []
        layers.append(f"  Technical:  {result.technical_signal.direction:4s} "
                      f"({result.technical_signal.strategy}, "
                      f"conf={result.technical_signal.confidence:.1%})")

        if result.ml_prediction:
            layers.append(f"  ML:         {result.ml_prediction['direction']:4s} "
                         f"(conf={result.ml_prediction['confidence']:.1%})")

        if result.ensemble_result:
            layers.append(f"  Ensemble:   {result.ensemble_result.get('direction', 'N/A'):4s} "
                         f"(consensus={result.ensemble_result.get('consensus', 'N/A')}, "
                         f"conf={result.ensemble_result.get('confidence', 0):.1%})")

        if result.news_sentiment and result.news_sentiment.get('sentiment'):
            sentiment = result.news_sentiment['sentiment']
            layers.append(f"  News:       {sentiment.get('sentiment', 'N/A'):10s} "
                         f"(alignment={sentiment.get('alignment', 'N/A')})")

        lines.extend(layers)
        lines.append("=" * 65)

        return "\n".join(lines)

    def format_summary(self, results: list[PipelineResult]) -> str:
        """Format a summary of all pipeline results."""
        actionable = [r for r in results if r.is_actionable()]
        holds = [r for r in results if not r.is_actionable()]

        lines = [
            "",
            "=" * 65,
            f"  PIPELINE SUMMARY - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 65,
            f"  Tickers analyzed: {len(set(r.ticker for r in results))}",
            f"  Total signals:    {len(results)}",
            f"  Actionable:       {len(actionable)}",
            f"  Hold:             {len(holds)}",
        ]

        if actionable:
            lines.append("")
            lines.append("-" * 65)
            lines.append("  ACTIONABLE SIGNALS:")
            lines.append("-" * 65)

            # Group by ticker
            by_ticker: dict[str, list[PipelineResult]] = {}
            for r in actionable:
                by_ticker.setdefault(r.ticker, []).append(r)

            for ticker, ticker_results in by_ticker.items():
                for r in ticker_results:
                    stars = '*' * r.confluence_score
                    lines.append(
                        f"  {r.ticker:8s} {r.interval:4s} | {r.final_direction:4s} "
                        f"| Conf: {r.final_confidence:.1%} "
                        f"| [{stars:5s}]"
                    )

        if holds:
            lines.append("")
            lines.append(f"  HOLD: {', '.join(sorted(set(r.ticker for r in holds)))}")

        lines.append("=" * 65)
        return "\n".join(lines)

    def format_telegram_message(self, result: PipelineResult) -> str:
        """Format a PipelineResult as plain text for Telegram."""
        stars = '*' * result.confluence_score + '.' * (5 - result.confluence_score)
        direction_emoji = '\U0001f7e2' if result.final_direction == 'BUY' else '\U0001f534'

        sig = result.technical_signal
        rr = sig.risk_reward_ratio
        rr_str = f"1:{rr:.1f}" if rr else "N/A"

        lines = [
            f"{direction_emoji} {result.final_direction} - {result.ticker}",
            f"Strategy: {sig.strategy} ({result.interval})",
            f"Confluence: [{stars}] ({result.confluence_score}/5)",
            "",
            f"Entry:  ${sig.entry_price:,.2f}",
        ]

        if sig.stop_loss:
            lines.append(f"SL:     ${sig.stop_loss:,.2f}")
        if sig.take_profit:
            lines.append(f"TP:     ${sig.take_profit:,.2f}")

        lines.append(f"R/R:    {rr_str}")
        lines.append(f"Conf:   {result.final_confidence:.0%}")

        if result.ml_prediction:
            lines.append(
                f"ML:     {result.ml_prediction['direction']} "
                f"({result.ml_prediction['confidence']:.0%})"
            )
        if result.ensemble_result:
            ens = result.ensemble_result
            lines.append(
                f"Ensemble: {ens.get('direction', 'N/A')} "
                f"({ens.get('consensus', 'N/A')})"
            )

        if result.news_sentiment and result.news_sentiment.get('sentiment'):
            try:
                from signals.news_analyzer import NewsAnalyzer
                analyzer = NewsAnalyzer()
                news_msg = analyzer.format_for_telegram(result.news_sentiment)
                if news_msg:
                    lines.append(news_msg)
            except Exception:
                pass

        lines.append(f"\n{result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

        return "\n".join(lines)

    def notify_actionable(self, results: list[PipelineResult]) -> int:
        """Send Telegram notifications for actionable results.

        Uses file-based dedup that persists across process invocations
        (Windows Task Scheduler creates a new process each hour).

        Args:
            results: Pipeline results to check.

        Returns:
            Number of notifications sent.
        """
        import time as _time

        if not self.send_telegram or not self.notifier.is_configured:
            return 0

        now = _time.time()
        DEDUP_SECONDS = 4 * 3600  # 4 hours

        # Load dedup state from file
        dedup_state: dict[str, float] = {}
        try:
            if self._dedup_file.exists():
                with open(self._dedup_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if ':' in line:
                            key, ts = line.split(':', 1)
                            dedup_state[key] = float(ts)
        except Exception as e:
            logger.debug(f"Failed to load dedup state: {e}")

        # Cleanup old entries (<= so signals at exactly the boundary are still deduped)
        dedup_state = {k: v for k, v in dedup_state.items() if now - v <= DEDUP_SECONDS}

        sent = 0
        for result in results:
            if result.is_actionable():
                dedup_key = f"{result.ticker}_{result.final_direction}"
                if dedup_key in dedup_state:
                    logger.debug(f"Skipping duplicate Telegram: {dedup_key}")
                    continue
                try:
                    msg = self.format_telegram_message(result)
                    self.notifier.send_alert(msg)
                    dedup_state[dedup_key] = now
                    sent += 1
                except Exception as e:
                    logger.warning(f"Telegram notification failed for {result.ticker}: {e}")

        # Save dedup state to file
        try:
            self._dedup_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._dedup_file, 'w') as f:
                for key, ts in dedup_state.items():
                    f.write(f"{key}:{ts}\n")
        except Exception as e:
            logger.debug(f"Failed to save dedup state: {e}")

        return sent

    def notify_health_check(self, results: list[PipelineResult]) -> bool:
        """Send a data freshness health summary via Telegram.

        Reports staleness per ticker and flags issues (yfinance fallback,
        data older than 24h, etc.). Only sends if health check is enabled
        in settings and there are any stale/problematic tickers.

        Returns:
            True if a message was sent, False otherwise.
        """
        if not self.send_telegram or not self.notifier.is_configured:
            return False
        if not TELEGRAM_HEALTH_CHECK_ENABLED:
            return False
        if not self._data_freshness:
            return False

        # Only report if there are problems
        problems = {k: v for k, v in self._data_freshness.items()
                    if 'stale' in v or 'fallback' in v or 'yfinance' in v or 'unknown' in v}
        if not problems:
            logger.debug("Health check: all tickers fresh, no alert sent")
            return False

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        lines = [f"⚠️ Data Health - {now_str}", ""]

        for key, status in sorted(problems.items()):
            lines.append(f"  {key}: {status}")

        lines.append("")
        lines.append(f"Total tickers: {len(self._data_freshness)}")
        lines.append(f"Problems: {len(problems)}")

        msg = "\n".join(lines)
        try:
            self.notifier.send_alert(msg)
            logger.info(f"Health check alert sent: {len(problems)} issues")
            return True
        except Exception as e:
            logger.warning(f"Health check alert failed: {e}")
            return False
