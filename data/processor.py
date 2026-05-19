"""
Data Processor Module
=====================
Cleans, validates, and prepares OHLCV DataFrames for analysis.
"""

import logging
from pathlib import Path

import pandas as pd

from config.settings import PROCESSED_DATA_DIR

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ['open', 'high', 'low', 'close', 'volume']


class DataProcessor:
    """Cleans and validates OHLCV market data."""

    @staticmethod
    def clean_data(df: pd.DataFrame) -> pd.DataFrame:
        """Clean OHLCV DataFrame: remove duplicates, NaN rows, sort by index.

        Args:
            df: Raw OHLCV DataFrame with DatetimeIndex.

        Returns:
            Cleaned DataFrame.
        """
        initial_len = len(df)

        # Ensure columns are flat (no MultiIndex leftovers)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(-1)
        df.columns = [str(c).lower().strip() for c in df.columns]

        # Remove duplicate columns
        df = df.loc[:, ~df.columns.duplicated(keep='first')]

        # Remove duplicate index entries
        df = df[~df.index.duplicated(keep='first')]

        # Sort by datetime
        df.sort_index(inplace=True)

        # Ensure index is timezone-naive UTC for consistent comparisons
        if hasattr(df.index, 'tz') and df.index.tz is not None:
            df.index = df.index.tz_convert('UTC').tz_localize(None)

        # Drop rows where all OHLCV values are NaN
        df.dropna(subset=REQUIRED_COLUMNS, how='all', inplace=True)

        # Forward-fill small gaps (e.g. missing single candle)
        for col in REQUIRED_COLUMNS:
            if col in df.columns:
                df[col] = df[col].ffill(limit=3)

        # Drop any remaining NaN rows
        df.dropna(subset=REQUIRED_COLUMNS, inplace=True)

        # Ensure volume is non-negative
        df['volume'] = df['volume'].clip(lower=0)

        removed = initial_len - len(df)
        if removed > 0:
            logger.info(f"Cleaned data: removed {removed} rows ({initial_len} -> {len(df)})")

        return df

    @staticmethod
    def validate_data(df: pd.DataFrame) -> bool:
        """Validate that DataFrame has correct OHLCV structure.

        Args:
            df: OHLCV DataFrame to validate.

        Returns:
            True if valid.

        Raises:
            ValueError: If validation fails.
        """
        # Check required columns
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        # Check not empty
        if df.empty:
            raise ValueError("DataFrame is empty")

        # Check index is datetime
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError(f"Index must be DatetimeIndex, got {type(df.index).__name__}")

        # Check no NaN in OHLCV
        nan_counts = df[REQUIRED_COLUMNS].isna().sum()
        cols_with_nan = nan_counts[nan_counts > 0]
        if not cols_with_nan.empty:
            raise ValueError(f"NaN values found: {cols_with_nan.to_dict()}")

        # Check OHLC logical consistency (high >= low)
        high_series = df['high']
        low_series = df['low']
        if isinstance(high_series, pd.DataFrame):
            high_series = high_series.iloc[:, 0]
        if isinstance(low_series, pd.DataFrame):
            low_series = low_series.iloc[:, 0]
        invalid_bars = df[high_series < low_series]
        if not invalid_bars.empty:
            raise ValueError(f"Found {len(invalid_bars)} bars where high < low")

        logger.info(f"Data validation passed: {len(df)} rows, {df.index[0]} to {df.index[-1]}")
        return True

    @staticmethod
    def save_processed(df: pd.DataFrame, ticker: str, interval: str = '') -> Path:
        """Save processed DataFrame to data/processed/.

        Args:
            df: Processed OHLCV DataFrame.
            ticker: Symbol for filename.
            interval: Optional interval for filename.

        Returns:
            Path to saved file.
        """
        safe_ticker = ticker.replace('/', '_').replace('-', '_')
        suffix = f"_{interval}" if interval else ''
        filename = f"{safe_ticker}{suffix}_processed.csv"
        filepath = PROCESSED_DATA_DIR / filename
        df.to_csv(filepath)
        logger.info(f"Saved processed data ({len(df)} rows) to {filepath}")
        return filepath
