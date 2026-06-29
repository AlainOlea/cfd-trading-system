"""
Tests for Incremental Data Fetch
=================================
Tests for rate limiter, metadata tracker, and incremental fetch methods.
"""

import json
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from data.rate_limiter import RateLimiter
from data.metadata import FetchMetadata


class TestRateLimiter:
    """Tests for token bucket rate limiter."""

    def test_acquire_single_token(self):
        """Should acquire token immediately when tokens available."""
        limiter = RateLimiter(200)  # 200 calls/min
        waited = limiter.acquire(1)
        assert waited == 0.0

    def test_acquire_multiple_tokens(self):
        """Should acquire multiple tokens at once."""
        limiter = RateLimiter(200)
        waited = limiter.acquire(10)
        assert waited == 0.0
        # Allow small float tolerance for time-based refill
        assert limiter.available_tokens < 191

    def test_rate_limit_enforcement(self):
        """Should block when tokens are depleted."""
        limiter = RateLimiter(200)  # ~3.33 tokens/sec

        # Consume all tokens
        for _ in range(200):
            limiter.acquire(1)

        # Should block now
        start = time.monotonic()
        limiter.acquire(1)
        elapsed = time.monotonic() - start

        # Should have waited ~0.3 seconds (1/3.33)
        assert elapsed >= 0.1

    def test_token_refill(self):
        """Should refill tokens over time."""
        limiter = RateLimiter(200)  # ~3.33 tokens/sec

        # Consume all tokens
        for _ in range(200):
            limiter.acquire(1)

        # Wait for refill
        time.sleep(0.5)

        # Should have ~1.67 tokens refilled (3.33 * 0.5)
        tokens = limiter.available_tokens
        assert tokens >= 1.0

    def test_thread_safety(self):
        """Should handle concurrent access safely."""
        limiter = RateLimiter(200)
        results = []

        def worker():
            limiter.acquire(1)
            results.append(True)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10


class TestFetchMetadata:
    """Tests for fetch metadata tracker."""

    def test_get_nonexistent(self):
        """Should return None for nonexistent ticker."""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = Path(f.name)

        try:
            meta = FetchMetadata(path)
            assert meta.get_last_fetch('SPY', '1d') is None
        finally:
            path.unlink()

    def test_set_and_get(self):
        """Should store and retrieve timestamps."""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = Path(f.name)

        try:
            meta = FetchMetadata(path)
            now = datetime.now(timezone.utc)
            meta.set_last_fetch('SPY', '1d', now, rows=250)

            result = meta.get_last_fetch('SPY', '1d')
            assert result is not None
            # Compare as UTC ISO strings
            assert result.isoformat() == now.isoformat()
        finally:
            path.unlink()

    def test_multiple_tickers(self):
        """Should track multiple tickers independently."""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = Path(f.name)

        try:
            meta = FetchMetadata(path)
            now = datetime.now(timezone.utc)

            meta.set_last_fetch('SPY', '1d', now)
            meta.set_last_fetch('QQQ', '1h', now + timedelta(hours=1))
            meta.set_last_fetch('BTC-USD', '1m', now + timedelta(minutes=5))

            assert meta.get_last_fetch('SPY', '1d') is not None
            assert meta.get_last_fetch('QQQ', '1h') is not None
            assert meta.get_last_fetch('BTC-USD', '1m') is not None
            assert meta.get_last_fetch('SPY', '1h') is None
        finally:
            path.unlink()

    def test_atomic_save(self):
        """Should save to JSON file atomically."""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = Path(f.name)

        try:
            meta = FetchMetadata(path)
            now = datetime.now(timezone.utc)
            meta.set_last_fetch('SPY', '1d', now, rows=250)

            # Verify file exists and contains data
            assert path.exists()
            with open(path) as f:
                data = json.load(f)
            assert 'SPY' in data
            assert data['SPY']['1d']['rows'] == 250
        finally:
            path.unlink()


class TestMergeDataframes:
    """Tests for DataFetcher._merge_dataframes."""

    def _make_df(self, dates, closes):
        """Helper to create test DataFrame."""
        return pd.DataFrame({
            'open': closes,
            'high': closes,
            'low': closes,
            'close': closes,
            'volume': [1000] * len(closes),
        }, index=pd.DatetimeIndex(dates, name='datetime'))

    def test_merge_new_overwrites_old(self):
        """New data should overwrite existing at same timestamps."""
        from data.fetcher import DataFetcher

        old = self._make_df(['2026-01-01', '2026-01-02'], [100, 101])
        new = self._make_df(['2026-01-02', '2026-01-03'], [200, 202])

        merged = DataFetcher._merge_dataframes(old, new)

        assert len(merged) == 3
        assert merged.loc['2026-01-02', 'close'] == 200  # New overwrites old

    def test_merge_empty_existing(self):
        """Should return new data when existing is empty."""
        from data.fetcher import DataFetcher

        old = pd.DataFrame()
        new = self._make_df(['2026-01-01'], [100])

        merged = DataFetcher._merge_dataframes(old, new)
        assert len(merged) == 1

    def test_merge_empty_new(self):
        """Should return existing data when new is empty."""
        from data.fetcher import DataFetcher

        old = self._make_df(['2026-01-01'], [100])
        new = pd.DataFrame()

        merged = DataFetcher._merge_dataframes(old, new)
        assert len(merged) == 1

    def test_merge_sorted(self):
        """Merged result should be sorted by date."""
        from data.fetcher import DataFetcher

        old = self._make_df(['2026-01-03', '2026-01-01'], [103, 101])
        new = self._make_df(['2026-01-02', '2026-01-04'], [102, 104])

        merged = DataFetcher._merge_dataframes(old, new)

        assert list(merged.index) == list(pd.DatetimeIndex([
            '2026-01-01', '2026-01-02', '2026-01-03', '2026-01-04'
        ]))

    def test_merge_tz_naive_and_aware(self):
        """Merge tz-naive CSV with tz-aware Alpaca data should not raise TypeError."""
        from data.fetcher import DataFetcher

        # CSV data (tz-naive, like yfinance)
        old = self._make_df(['2026-01-01', '2026-01-02'], [100, 101])

        # Alpaca data (tz-aware UTC)
        new = self._make_df(['2026-01-02', '2026-01-03'], [200, 202])
        new.index = new.index.tz_localize('UTC')

        # This used to raise: TypeError: Cannot compare tz-naive and tz-aware
        merged = DataFetcher._merge_dataframes(old, new)

        assert len(merged) == 3
        assert merged.index.tz is None  # Result should be tz-naive
        assert merged.loc['2026-01-02', 'close'] == 200
