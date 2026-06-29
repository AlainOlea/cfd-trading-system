"""
Data Fetcher Module
==================
Downloads OHLCV data from Yahoo Finance, CCXT (Bitso) exchanges,
and Alpaca Data API (incremental).
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ccxt
import pandas as pd
import yfinance as yf

from config.settings import (
    ALPACA_DATA_DEFAULT_CHUNK_DAYS,
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

try:
    from data.alpaca_data import AlpacaDataFetcher
    from data.metadata import FetchMetadata
    ALPACA_DATA_AVAILABLE = True
except ImportError:
    ALPACA_DATA_AVAILABLE = False

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

    # ============================================
    # INCREMENTAL FETCH (Alpaca Data API)
    # ============================================

    def fetch_incremental(
        self,
        ticker: str,
        interval: str,
        chunk_days: int = None,
    ) -> pd.DataFrame:
        """Fetch data incrementally using Alpaca Data API.

        Only fetches new data since last fetch. Merges with existing CSV.
        Falls back to yfinance if Alpaca is unavailable.

        Args:
            ticker: Symbol (e.g. 'SPY', 'BTC-USD').
            interval: Data interval ('1m', '1h', '1d').
            chunk_days: Days per batch chunk. Uses default if None.

        Returns:
            Merged DataFrame with all data (existing + new).
        """
        if not ALPACA_DATA_AVAILABLE:
            logger.warning("Alpaca Data API unavailable, falling back to yfinance")
            return self.fetch_yfinance(ticker, interval, days=365)

        metadata = FetchMetadata()
        last_fetch = metadata.get_last_fetch(ticker, interval)

        # Determine start date for incremental fetch
        if last_fetch:
            start = last_fetch
            logger.info(f"Incremental fetch {ticker} {interval} from {start.isoformat()}")
        else:
            # No metadata: try to infer start from existing CSV last row
            try:
                existing_df = self.load_from_csv(ticker, interval)
                last_ts = existing_df.index[-1]
                # Convert naive UTC timestamp to aware
                if last_ts.tzinfo is None:
                    last_ts = last_ts.replace(tzinfo=timezone.utc)
                start = last_ts
                logger.info(f"Incremental fetch {ticker} {interval} from CSV last: {start.isoformat()}")
            except (FileNotFoundError, IndexError, KeyError):
                # No CSV either: fetch 1 year for 1d/1h, 90 days for 1m
                days_back = 365 if interval != '1m' else 90
                start = datetime.now(timezone.utc) - timedelta(days=days_back)
                logger.info(f"First fetch {ticker} {interval}: {days_back}d from {start.date()}")

        end = datetime.now(timezone.utc)

        # Guard: Alpaca free tier has a 15-min delay, so the effective end
        # for the API call is (end - 15min). If CSV data is newer than that,
        # there's nothing new to fetch.
        alpaca_end = end - timedelta(minutes=15)
        if start >= alpaca_end:
            logger.info(f"No new data to fetch for {ticker} {interval} "
                        f"(CSV up to {start.strftime('%H:%M')}, "
                        f"Alpaca delay until {alpaca_end.strftime('%H:%M')})")
            try:
                return self.load_from_csv(ticker, interval)
            except FileNotFoundError:
                raise ValueError(f"No data available for {ticker} {interval}")

        # Fetch from Alpaca
        alpaca = AlpacaDataFetcher()
        new_data = alpaca.fetch_bars([ticker], interval, start, end)

        if ticker not in new_data or new_data[ticker].empty:
            logger.warning(f"No new data from Alpaca for {ticker} {interval}")
            # Try loading existing CSV
            try:
                return self.load_from_csv(ticker, interval)
            except FileNotFoundError:
                raise ValueError(f"No data available for {ticker} {interval}")

        new_df = new_data[ticker]

        # Merge with existing CSV
        try:
            existing_df = self.load_from_csv(ticker, interval)
            merged = self._merge_dataframes(existing_df, new_df)
        except FileNotFoundError:
            merged = new_df

        # Save merged data
        self.save_to_csv(merged, ticker, interval)

        # Update metadata
        metadata.set_last_fetch(
            ticker, interval, datetime.now(timezone.utc), len(merged)
        )

        logger.info(f"Incremental fetch complete: {len(merged)} rows for {ticker} {interval}")
        return merged

    def fetch_incremental_batch(
        self,
        tickers: list[str],
        interval: str,
        chunk_days: int = None,
    ) -> dict[str, pd.DataFrame]:
        """Fetch data for multiple tickers incrementally.

        Args:
            tickers: List of ticker symbols.
            interval: Data interval.
            chunk_days: Days per batch chunk.

        Returns:
            Dict mapping ticker -> DataFrame.
        """
        results = {}
        for ticker in tickers:
            try:
                results[ticker] = self.fetch_incremental(ticker, interval, chunk_days)
            except Exception as e:
                logger.error(f"Failed to fetch {ticker} {interval}: {e}")
        return results

    def fetch_1min_history(
        self,
        tickers: list[str],
        years: int = 3,
        chunk_days: int = None,
    ) -> dict[str, pd.DataFrame]:
        """Fetch 1-minute historical data for model training.

        Uses Alpaca Data API with batch fetching by date ranges.

        Args:
            tickers: List of ticker symbols.
            years: Years of history to fetch (max ~7 for stocks, ~5 for crypto).
            chunk_days: Days per batch chunk (default from settings).

        Returns:
            Dict mapping ticker -> DataFrame with 1-min bars.
        """
        if not ALPACA_DATA_AVAILABLE:
            raise ImportError("Alpaca Data API required for 1-min history")

        chunk = chunk_days or ALPACA_DATA_DEFAULT_CHUNK_DAYS
        total_days = years * 365

        alpaca = AlpacaDataFetcher()
        results = alpaca.fetch_batch_ranges(tickers, '1m', total_days, chunk)

        # Save each ticker
        for ticker, df in results.items():
            self.save_to_csv(df, ticker, '1m')

        # Update metadata
        metadata = FetchMetadata()
        now = datetime.now(timezone.utc)
        for ticker in results:
            metadata.set_last_fetch(ticker, '1m', now, len(results[ticker]))

        return results

    @staticmethod
    def _merge_dataframes(
        existing: pd.DataFrame, new: pd.DataFrame
    ) -> pd.DataFrame:
        """Merge two DataFrames, new data overwrites existing at same index.

        Args:
            existing: Current CSV data.
            new: Newly fetched data.

        Returns:
            Merged DataFrame sorted by date.
        """
        if existing.empty:
            return new
        if new.empty:
            return existing

        # Normalize timezone: strip tz from both to avoid tz-naive vs tz-aware errors
        if existing.index.tz is not None:
            existing.index = existing.index.tz_localize(None)
        if new.index.tz is not None:
            new.index = new.index.tz_localize(None)

        # Concat, new overwrites existing at same timestamps
        merged = pd.concat([existing, new])
        merged = merged[~merged.index.duplicated(keep='last')]
        merged.sort_index(inplace=True)
        return merged
