"""
Alpaca Data API Wrapper
========================
Fetches historical OHLCV bars from Alpaca's free market data API.
Supports stocks, ETFs, and crypto with automatic routing.
Handles pagination and rate limiting.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from data.rate_limiter import RateLimiter

load_dotenv()

logger = logging.getLogger(__name__)

try:
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.historical.crypto import CryptoHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    from alpaca.data.enums import DataFeed

    ALPACA_DATA_AVAILABLE = True
except ImportError:
    ALPACA_DATA_AVAILABLE = False
    logger.warning("alpaca-py not installed. Install with: pip install alpaca-py")

# Mapping from our interval format to Alpaca TimeFrame
INTERVAL_MAP = {
    '1m': TimeFrame.Minute if ALPACA_DATA_AVAILABLE else None,
    '5m': TimeFrame(5, TimeFrameUnit.Minute) if ALPACA_DATA_AVAILABLE else None,
    '15m': TimeFrame(15, TimeFrameUnit.Minute) if ALPACA_DATA_AVAILABLE else None,
    '30m': TimeFrame(30, TimeFrameUnit.Minute) if ALPACA_DATA_AVAILABLE else None,
    '1h': TimeFrame.Hour if ALPACA_DATA_AVAILABLE else None,
    '1d': TimeFrame.Day if ALPACA_DATA_AVAILABLE else None,
}

# Crypto symbols that Alpaca supports
ALPACA_CRYPTO_SYMBOLS = {'BTC-USD', 'ETH-USD', 'SOL-USD', 'XRP-USD', 'DOGE-USD'}


def _to_alpaca_crypto(ticker: str) -> str:
    """Convert our crypto format to Alpaca format.
    'BTC-USD' -> 'BTC/USD'
    """
    return ticker.replace('-', '/')


def _is_crypto_ticker(ticker: str) -> bool:
    """Check if a ticker is crypto."""
    return ticker in ALPACA_CRYPTO_SYMBOLS


class AlpacaDataFetcher:
    """Wrapper for Alpaca Data API with rate limiting and pagination."""

    def __init__(self, rate_limiter: RateLimiter = None):
        """Initialize Alpaca Data API clients.

        Args:
            rate_limiter: RateLimiter instance. If None, creates one with 200 calls/min.
        """
        if not ALPACA_DATA_AVAILABLE:
            raise ImportError("alpaca-py not installed")

        api_key = os.getenv('ALPACA_API_KEY', '')
        secret_key = os.getenv('ALPACA_SECRET_KEY', '')

        self.rate_limiter = rate_limiter or RateLimiter(200)

        if api_key and secret_key:
            self.stock_client = StockHistoricalDataClient(api_key, secret_key)
            self.crypto_client = CryptoHistoricalDataClient(api_key, secret_key)
            logger.info("Alpaca Data API initialized with API keys")
        else:
            # Crypto client works without keys (lower rate limit)
            self.stock_client = None
            self.crypto_client = CryptoHistoricalDataClient()
            logger.warning("Alpaca Data API initialized without API keys (crypto only)")

    def fetch_bars(
        self,
        symbols: list[str],
        interval: str,
        start: datetime,
        end: datetime = None,
    ) -> dict[str, pd.DataFrame]:
        """Fetch OHLCV bars for multiple symbols.

        Automatically routes stocks vs crypto and handles pagination.

        Args:
            symbols: List of ticker symbols.
            interval: Data interval ('1m', '5m', '15m', '1h', '1d').
            start: Start datetime (UTC).
            end: End datetime (UTC). If None, uses current time.

        Returns:
            Dict mapping ticker -> DataFrame with OHLCV columns.
        """
        if not symbols:
            return {}

        timeframe = INTERVAL_MAP.get(interval)
        if timeframe is None:
            raise ValueError(f"Unsupported interval: {interval}")

        # Free tier: REST API has 15-minute delay on IEX feed
        # Adjust end time to avoid querying recent data that's not yet available
        if end is not None:
            end = end - timedelta(minutes=15)
        else:
            end = datetime.now(timezone.utc) - timedelta(minutes=15)

        # Separate stocks vs crypto
        stock_symbols = [s for s in symbols if not _is_crypto_ticker(s)]
        crypto_symbols = [s for s in symbols if _is_crypto_ticker(s)]

        results = {}

        # Fetch stocks
        if stock_symbols and self.stock_client:
            results.update(self._fetch_stock_bars(stock_symbols, timeframe, start, end))

        # Fetch crypto
        if crypto_symbols:
            results.update(self._fetch_crypto_bars(crypto_symbols, timeframe, start, end))

        return results

    def _fetch_stock_bars(
        self,
        symbols: list[str],
        timeframe,
        start: datetime,
        end: datetime = None,
    ) -> dict[str, pd.DataFrame]:
        """Fetch stock bars with pagination."""
        all_results = {}

        try:
            self.rate_limiter.acquire()
            request = StockBarsRequest(
                symbol_or_symbols=symbols,
                timeframe=timeframe,
                start=start,
                end=end,
                feed=DataFeed.IEX,
            )
            bars = self.stock_client.get_stock_bars(request)

            # Extract per-symbol data (bars[symbol] returns list of Bar objects)
            for symbol in symbols:
                try:
                    symbol_bars = bars[symbol]
                    df = self._bars_to_df(symbol_bars)
                    if not df.empty:
                        all_results[symbol] = df
                except (KeyError, IndexError):
                    logger.warning(f"No data returned for {symbol}")

        except Exception as e:
            logger.error(f"Alpaca stock bars fetch failed: {e}")
            raise

        return all_results

    def _fetch_stock_bars_paginated(
        self,
        symbol: str,
        timeframe,
        start: datetime,
        end: datetime,
        results: dict,
    ):
        """Fetch additional pages for a stock symbol."""
        try:
            self.rate_limiter.acquire()
            request = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=timeframe,
                start=start,
                end=end,
                limit=10000,
                feed=DataFeed.IEX,
            )
            bars = self.stock_client.get_stock_bars(request)
            if symbol in bars and not bars[symbol].df.empty:
                existing = results.get(symbol, pd.DataFrame())
                new_data = self._bars_to_df(bars[symbol])
                if not existing.empty:
                    results[symbol] = pd.concat([existing, new_data]).sort_index()
                else:
                    results[symbol] = new_data
        except Exception as e:
            logger.warning(f"Pagination failed for {symbol}: {e}")

    def _fetch_crypto_bars(
        self,
        symbols: list[str],
        timeframe,
        start: datetime,
        end: datetime = None,
    ) -> dict[str, pd.DataFrame]:
        """Fetch crypto bars."""
        all_results = {}

        # Convert to Alpaca format: 'BTC-USD' -> 'BTC/USD'
        alpaca_symbols = [_to_alpaca_crypto(s) for s in symbols]

        try:
            self.rate_limiter.acquire()
            request = CryptoBarsRequest(
                symbol_or_symbols=alpaca_symbols,
                timeframe=timeframe,
                start=start,
                end=end,
            )
            bars = self.crypto_client.get_crypto_bars(request)

            # Map back to our format
            for original, alpaca in zip(symbols, alpaca_symbols):
                try:
                    symbol_bars = bars[alpaca]
                    df = self._bars_to_df(symbol_bars)
                    if not df.empty:
                        all_results[original] = df
                except (KeyError, IndexError):
                    logger.warning(f"No crypto data returned for {original}")

        except Exception as e:
            logger.error(f"Alpaca crypto bars fetch failed: {e}")
            raise

        return all_results

    def _bars_to_df(self, bars) -> pd.DataFrame:
        """Convert Alpaca bars to our standard DataFrame format."""
        if hasattr(bars, 'df'):
            df = bars.df.copy()
        elif isinstance(bars, list) and len(bars) > 0 and hasattr(bars[0], 'open'):
            # bars[symbol] returns a list of Bar objects
            df = pd.DataFrame([{
                'timestamp': bar.timestamp,
                'open': bar.open,
                'high': bar.high,
                'low': bar.low,
                'close': bar.close,
                'volume': bar.volume,
            } for bar in bars])
        else:
            return pd.DataFrame()

        # Normalize columns
        df.columns = [c.lower().strip() for c in df.columns]

        # Ensure DatetimeIndex
        if 'timestamp' in df.columns:
            df['datetime'] = pd.to_datetime(df['timestamp'])
            df.set_index('datetime', inplace=True)
            df.drop(columns=['timestamp'], inplace=True, errors='ignore')
        elif df.index.name != 'datetime':
            df.index.name = 'datetime'

        # Ensure OHLCV columns
        expected = ['open', 'high', 'low', 'close', 'volume']
        for col in expected:
            if col not in df.columns:
                df[col] = 0.0

        return df[expected].astype(float)

    def fetch_batch_ranges(
        self,
        symbols: list[str],
        interval: str,
        total_days: int,
        chunk_days: int = 90,
    ) -> dict[str, pd.DataFrame]:
        """Fetch historical data in date range chunks.

        Useful for getting large amounts of historical data (e.g. 3 years of 1min bars)
        while respecting API limits.

        Args:
            symbols: List of ticker symbols.
            interval: Data interval.
            total_days: Total calendar days to fetch.
            chunk_days: Days per chunk (default 90).

        Returns:
            Dict mapping ticker -> merged DataFrame.
        """
        results: dict[str, pd.DataFrame] = {}
        # Free tier has 15-minute delay on REST API, so end 15 min ago
        end = datetime.now(timezone.utc) - timedelta(minutes=15)
        remaining = total_days

        while remaining > 0:
            chunk_end = end
            chunk_start = end - timedelta(days=min(chunk_days, remaining))

            logger.info(
                f"Batch fetch {interval}: "
                f"{chunk_start.strftime('%Y-%m-%d')} to {chunk_end.strftime('%Y-%m-%d')}"
            )

            try:
                chunk_data = self.fetch_bars(symbols, interval, chunk_start, chunk_end)

                for symbol, df in chunk_data.items():
                    if symbol not in results:
                        results[symbol] = df
                    else:
                        results[symbol] = pd.concat([results[symbol], df])

            except Exception as e:
                logger.warning(f"Batch chunk failed ({chunk_start}-{chunk_end}): {e}")

            end = chunk_start
            remaining -= chunk_days

        # Dedup and sort
        for symbol in results:
            results[symbol] = results[symbol][~results[symbol].index.duplicated(keep='last')]
            results[symbol].sort_index(inplace=True)

        return results
