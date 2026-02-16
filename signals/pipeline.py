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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from config.settings import MARKET_HOURS, TICKERS as TICKER_GROUPS, PIPELINE_TICKERS_RAW
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
    final_direction: str = 'HOLD'       # BUY/SELL/HOLD
    final_confidence: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def is_actionable(self) -> bool:
        """Check if this result has an actionable signal."""
        return self.final_direction in ('BUY', 'SELL')

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
        self.max_workers = max_workers

        self.fetcher = DataFetcher()
        self.processor = DataProcessor()
        self.generator = SignalGenerator()
        self.manager = SignalManager()
        self.notifier = TelegramNotifier()

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
                logger.error(f"Pipeline error for {config.ticker} {interval}: {e}")

        # Compute multi-timeframe confluence across all intervals
        if len(results) > 1:
            confluence = self._compute_confluence(results)
            for r in results:
                r.confluence_score = confluence

        return results

    def run_all(
        self,
        configs: list[TickerConfig] | None = None,
        category: str | None = None,
        ticker_filter: str | None = None,
    ) -> list[PipelineResult]:
        """Execute pipeline for all configured tickers.

        Args:
            configs: List of TickerConfig. If None, uses PIPELINE_TICKERS from settings.
            category: Filter by category ('indices', 'stocks', 'crypto', 'commodities').
            ticker_filter: Run for a specific ticker only.

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
                    logger.error(f"Pipeline failed for {config.ticker}: {e}")

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

        # 2. Apply strategies directly on the fresh DataFrame (no re-fetch)
        best_signal = None
        for strategy_name in config.strategies:
            try:
                if strategy_name not in STRATEGY_MAP:
                    logger.warning(f"Unknown strategy: {strategy_name}")
                    continue

                strategy = STRATEGY_MAP[strategy_name]()
                signals_df = strategy.generate_signals(df.copy())
                latest = signals_df.iloc[-1]

                signal = Signal(
                    strategy=strategy_name,
                    ticker=config.ticker,
                    interval=interval,
                    direction=latest['signal'],
                    entry_price=float(latest['close']),
                    stop_loss=float(latest['stop_loss']),
                    take_profit=float(latest['take_profit']),
                    confidence=float(latest['confidence']),
                )

                # Pick the most actionable signal (BUY/SELL over HOLD, highest confidence)
                if best_signal is None:
                    best_signal = signal
                elif signal.direction != 'HOLD' and (
                    best_signal.direction == 'HOLD' or signal.confidence > best_signal.confidence
                ):
                    best_signal = signal
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
        """Fetch FRESH data for a ticker+interval from Yahoo Finance.

        Always fetches live data to ensure signals are based on current prices.
        Saves to CSV as backup after fetching.
        """
        days = self.generator._estimate_days(interval)
        logger.info(f"Fetching fresh data for {ticker} {interval} ({days}d)")
        df = self.fetcher.fetch_yfinance(ticker, interval, days)
        df = self.processor.clean_data(df)
        self.processor.validate_data(df)
        self.fetcher.save_to_csv(df, ticker, interval)
        df = TechnicalIndicators.add_all_indicators(df)
        return df

    def _apply_ml(self, ticker: str, interval: str, df: pd.DataFrame) -> dict | None:
        """Apply single ML model prediction."""
        try:
            from models.predictor import PricePredictor
            predictor = PricePredictor(confidence_threshold=0.55)
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

        Stars are awarded for:
        1. Multiple timeframes agree on direction
        2. ML confirms the direction
        3. Ensemble has STRONG consensus
        4. News sentiment aligns
        5. High confidence across all layers

        Args:
            results: PipelineResults for the same ticker across intervals.

        Returns:
            Score from 0 to 5.
        """
        if not results:
            return 0

        stars = 0
        directions = [r.final_direction for r in results if r.final_direction != 'HOLD']

        if not directions:
            return 0

        # Star 1: At least one actionable signal
        stars += 1

        # Star 2: Multiple timeframes agree
        if len(directions) >= 2 and len(set(directions)) == 1:
            stars += 1

        # Star 3: ML confirms (any interval)
        ml_confirms = any(
            r.ml_prediction and r.ml_prediction.get('direction') == r.final_direction
            for r in results if r.final_direction != 'HOLD'
        )
        if ml_confirms:
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

        return stars

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
        """Format a PipelineResult for Telegram notification.

        Uses Telegram MarkdownV1-safe formatting: backticks for values,
        avoids unmatched * and special chars in dynamic content.
        """
        stars_emoji = '\u2b50' * result.confluence_score
        direction_emoji = '\U0001f7e2' if result.final_direction == 'BUY' else '\U0001f534'

        sig = result.technical_signal
        rr = sig.risk_reward_ratio
        rr_str = f"1:{rr:.1f}" if rr else "N/A"

        lines = [
            f"{direction_emoji} *{result.final_direction}* - `{result.ticker}`",
            f"Strategy: `{sig.strategy}` ({result.interval})",
            f"Confluence: {stars_emoji} ({result.confluence_score}/5)",
            "",
            f"Entry:  `${sig.entry_price:,.2f}`",
        ]

        if sig.stop_loss:
            lines.append(f"SL:     `${sig.stop_loss:,.2f}`")
        if sig.take_profit:
            lines.append(f"TP:     `${sig.take_profit:,.2f}`")

        lines.append(f"R/R:    `{rr_str}`")
        lines.append(f"Conf:   `{result.final_confidence:.0%}`")

        # Layers summary
        if result.ml_prediction:
            lines.append(
                f"ML:     `{result.ml_prediction['direction']} "
                f"({result.ml_prediction['confidence']:.0%})`"
            )
        if result.ensemble_result:
            ens = result.ensemble_result
            lines.append(
                f"Ensemble: `{ens.get('direction', 'N/A')} "
                f"({ens.get('consensus', 'N/A')})`"
            )

        # News context
        if result.news_sentiment and result.news_sentiment.get('sentiment'):
            try:
                from signals.news_analyzer import NewsAnalyzer
                analyzer = NewsAnalyzer()
                news_msg = analyzer.format_for_telegram(result.news_sentiment)
                if news_msg:
                    lines.append(news_msg)
            except Exception:
                pass

        lines.append(f"\n_{result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}_")

        return "\n".join(lines)

    def notify_actionable(self, results: list[PipelineResult]) -> int:
        """Send Telegram notifications for actionable results.

        Args:
            results: Pipeline results to check.

        Returns:
            Number of notifications sent.
        """
        if not self.send_telegram or not self.notifier.is_configured:
            return 0

        sent = 0
        for result in results:
            if result.is_actionable():
                try:
                    msg = self.format_telegram_message(result)
                    self.notifier.send_alert(msg)
                    sent += 1
                except Exception as e:
                    logger.warning(f"Telegram notification failed for {result.ticker}: {e}")
        return sent
