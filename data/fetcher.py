"""
Data Fetcher Module
===================
Downloads OHLCV data from Yahoo Finance and CCXT (Bitso) exchanges.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

import ccxt
import pandas as pd
import yfinance as yf

from config.settings import (
    BITSO_API_KEY,
    BITSO_API_SECRET,
    CCXT_ENABLE_RATEIMIT,
    CCXT_EXCHANGE,
    CCXT_TIMEOUT,
    RAW_DATA_DIR,
    YFINANCE_AUTO_ADJUST,
    YFINANCE_PREPOST,
    YFINANCE_THREADS,
)

logger = logging.getLogger(__name__)

# CCXT timeframe mapping from yfinance-style intervals
CCXT_TIMEFRAME_MAP = {
    '1m': '1m',
    '5m': '5m',
    '15m': '15m',
    '1h': '1h',
    '1d': '1d',
}


class DataFetcher:
    """Fetches OHLCV market data from multiple sources."""

    def __init__(self):
        self._exchange = None

    @property
    def exchange(self) -> ccxt.Exchange:
        """Lazy-load CCXT exchange connection."""
        if self._exchange is None:
            exchange_class = getattr(ccxt, CCXT_EXCHANGE)
            config = {
                'enableRateLimit': CCXT_ENABLE_RATEIMIT,
                'timeout': CCXT_TIMEOUT,
            }
            if BITSO_API_KEY and BITSO_API_SECRET:
                config['apiKey'] = BITSO_API_KEY
                config['secret'] = BITSO_API_SECRET
            self._exchange = exchange_class(config)
        return self._exchange

    def fetch_yfinance(
        self, ticker: str, interval: str = '1d', days: int = 30
    ) -> pd.DataFrame:
        """Download OHLCV data from Yahoo Finance.

        Args:
            ticker: Symbol (e.g. 'SPY', 'GLD', 'BTC-USD').
            interval: Data interval ('1m','5m','15m','1h','1d').
            days: Number of calendar days of history.

        Returns:
            DataFrame with columns [open, high, low, close, volume] and
            a DatetimeIndex named 'datetime'.
        """
        end = datetime.now()
        start = end - timedelta(days=days)

        logger.info(f"Fetching {ticker} from Yahoo Finance ({interval}, {days}d)")

        data = yf.download(
            ticker,
            start=start.strftime('%Y-%m-%d'),
            end=end.strftime('%Y-%m-%d'),
            interval=interval,
            auto_adjust=YFINANCE_AUTO_ADJUST,
            prepost=YFINANCE_PREPOST,
            threads=YFINANCE_THREADS,
            progress=False,
        )

        if data.empty:
            raise ValueError(f"No data returned for {ticker} ({interval}, {days}d)")

        df = self._normalize_columns(data)
        logger.info(f"Fetched {len(df)} rows for {ticker}")
        return df

    def fetch_ccxt(
        self, symbol: str, timeframe: str = '1d', limit: int = 500
    ) -> pd.DataFrame:
        """Download OHLCV data from CCXT exchange (Bitso).

        Args:
            symbol: Trading pair (e.g. 'BTC/MXN', 'ETH/MXN').
            timeframe: Candle timeframe ('1m','5m','15m','1h','1d').
            limit: Max number of candles to fetch.

        Returns:
            DataFrame with columns [open, high, low, close, volume].
        """
        ccxt_tf = CCXT_TIMEFRAME_MAP.get(timeframe, timeframe)
        logger.info(f"Fetching {symbol} from {CCXT_EXCHANGE} ({ccxt_tf}, limit={limit})")

        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=ccxt_tf, limit=limit)

        if not ohlcv:
            raise ValueError(f"No data returned for {symbol} from {CCXT_EXCHANGE}")

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('datetime', inplace=True)
        df.drop(columns=['timestamp'], inplace=True)
        df = df.astype(float)

        logger.info(f"Fetched {len(df)} rows for {symbol}")
        return df

    def save_to_csv(self, df: pd.DataFrame, ticker: str, interval: str) -> Path:
        """Save DataFrame to CSV in data/raw/.

        Args:
            df: OHLCV DataFrame.
            ticker: Symbol used for filename.
            interval: Interval used for filename.

        Returns:
            Path to saved file.
        """
        safe_ticker = ticker.replace('/', '_').replace('-', '_')
        filename = f"{safe_ticker}_{interval}.csv"
        filepath = RAW_DATA_DIR / filename
        df.to_csv(filepath)
        logger.info(f"Saved {len(df)} rows to {filepath}")
        return filepath

    def fetch_bulk(
        self,
        ticker: str,
        interval: str,
        total_days: int = 2190,
        chunk_days: int | None = None,
    ) -> pd.DataFrame:
        """Fetch historical data in chunks, bypassing yfinance limits.

        Yahoo Finance limits 1h/15m/5m data to ~730 days per request.
        This method splits the range into chunks, fetches each chunk,
        and merges them into one clean DataFrame.

        Args:
            ticker: Symbol (e.g. 'SPY', 'BTC-USD').
            interval: Data interval ('1d','1h','15m','5m').
            total_days: Total calendar days to fetch.
            chunk_days: Days per chunk (auto-set per interval).

        Returns:
            Merged OHLCV DataFrame sorted by date.
        """
        # Auto-set chunk size based on yfinance limits
        if chunk_days is None:
            if interval in ('1d',):
                chunk_days = total_days  # 1d has no limit, one fetch
            else:
                chunk_days = 700  # Safe margin under 730-day limit

        from datetime import datetime, timedelta

        end = datetime.now()
        chunks = []
        remaining = total_days

        while remaining > 0:
            chunk_start = end - timedelta(days=min(chunk_days, remaining))
            logger.info(
                f"Bulk fetch {ticker} {interval}: "
                f"{chunk_start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"
            )

            try:
                data = yf.download(
                    ticker,
                    start=chunk_start.strftime('%Y-%m-%d'),
                    end=end.strftime('%Y-%m-%d'),
                    interval=interval,
                    auto_adjust=YFINANCE_AUTO_ADJUST,
                    prepost=YFINANCE_PREPOST,
                    threads=YFINANCE_THREADS,
                    progress=False,
                )
                if not data.empty:
                    df = self._normalize_columns(data)
                    chunks.append(df)
            except Exception as e:
                logger.warning(f"Chunk failed for {ticker}: {e}")

            end = chunk_start
            remaining -= chunk_days

        if not chunks:
            raise ValueError(f"No data returned for {ticker} across {total_days}d")

        merged = pd.concat(chunks)
        merged = merged[~merged.index.duplicated(keep='first')]
        merged.sort_index(inplace=True)
        logger.info(f"Bulk fetch complete: {len(merged)} rows for {ticker}")
        return merged

    def load_from_csv(self, ticker: str, interval: str) -> pd.DataFrame:
        """Load DataFrame from CSV in data/raw/.

        Args:
            ticker: Symbol used for filename.
            interval: Interval used for filename.

        Returns:
            OHLCV DataFrame.

        Raises:
            FileNotFoundError: If CSV does not exist.
        """
        safe_ticker = ticker.replace('/', '_').replace('-', '_')
        filename = f"{safe_ticker}_{interval}.csv"
        filepath = RAW_DATA_DIR / filename

        if not filepath.exists():
            raise FileNotFoundError(f"No data file found at {filepath}")

        df = pd.read_csv(filepath, index_col=0, parse_dates=True)
        df.index.name = 'datetime'
        logger.info(f"Loaded {len(df)} rows from {filepath}")
        return df

    @staticmethod
    def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names to lowercase and flatten MultiIndex."""
        # yfinance may return MultiIndex columns for single ticker
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df.columns = [c.lower().strip() for c in df.columns]

        expected = ['open', 'high', 'low', 'close', 'volume']
        missing = [c for c in expected if c not in df.columns]
        if missing:
            raise ValueError(f"Missing columns after normalization: {missing}")

        df = df[expected].copy()
        df.index.name = 'datetime'
        return df
