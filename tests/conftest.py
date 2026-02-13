"""
Shared test fixtures for the CFD Trading System.
"""

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_ohlcv_df():
    """Generate a synthetic OHLCV DataFrame for testing (100 rows)."""
    np.random.seed(42)
    n = 100
    dates = pd.date_range('2025-01-01', periods=n, freq='1D')

    # Random walk price
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.abs(np.random.randn(n) * 0.3)
    low = close - np.abs(np.random.randn(n) * 0.3)
    open_ = close + np.random.randn(n) * 0.2
    volume = np.random.randint(1_000_000, 10_000_000, n).astype(float)

    df = pd.DataFrame({
        'open': open_,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
    }, index=dates)
    return df


@pytest.fixture
def large_ohlcv_df():
    """Generate a larger OHLCV DataFrame (300 rows) for indicator warmup."""
    np.random.seed(123)
    n = 300
    dates = pd.date_range('2024-01-01', periods=n, freq='1D')

    close = 500 + np.cumsum(np.random.randn(n) * 2)
    high = close + np.abs(np.random.randn(n) * 1.0)
    low = close - np.abs(np.random.randn(n) * 1.0)
    open_ = close + np.random.randn(n) * 0.5
    volume = np.random.randint(5_000_000, 50_000_000, n).astype(float)

    df = pd.DataFrame({
        'open': open_,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
    }, index=dates)
    return df


@pytest.fixture
def df_with_indicators(large_ohlcv_df):
    """Large OHLCV DataFrame with all indicators already computed."""
    from indicators.technical import TechnicalIndicators
    return TechnicalIndicators.add_all_indicators(large_ohlcv_df)
