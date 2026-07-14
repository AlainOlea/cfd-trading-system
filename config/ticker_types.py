"""
Typed shape for per-ticker pipeline configuration.

Lives here (outside signals/pipeline.py) so config/settings.py can build
PIPELINE_TICKERS as a list of typed TickerConfig objects directly, instead of
positional tuples re-parsed at import time. settings.py can't import from
signals.pipeline to get TickerConfig there: pipeline.py itself imports from
config.settings, so that direction would be circular. This module has no
dependency on signals.pipeline, so both sides can import it freely.
"""

from dataclasses import dataclass


@dataclass
class TickerConfig:
    """Configuration per ticker for the pipeline."""
    ticker: str
    category: str                   # indices, stocks, crypto, commodities
    intervals: list[str]            # ['1d', '1h', '15m']
    strategies: list[str]           # ['macd_vwap', 'rsi_bb']
    use_ml: bool = True
    use_news: bool = True
    confluence_min_stars: int = 2   # minimum to consider actionable
