"""Tests for data fetcher and processor modules."""

import pandas as pd
import pytest

from data.processor import DataProcessor


class TestDataProcessor:
    """Tests for DataProcessor."""

    def test_clean_data_removes_duplicates(self, sample_ohlcv_df):
        # Add duplicate rows
        df = pd.concat([sample_ohlcv_df, sample_ohlcv_df.iloc[:5]])
        cleaned = DataProcessor.clean_data(df)
        assert not cleaned.index.duplicated().any()

    def test_clean_data_sorts_index(self, sample_ohlcv_df):
        df = sample_ohlcv_df.iloc[::-1]  # Reverse order
        cleaned = DataProcessor.clean_data(df)
        assert cleaned.index.is_monotonic_increasing

    def test_clean_data_clips_negative_volume(self, sample_ohlcv_df):
        df = sample_ohlcv_df.copy()
        df.loc[df.index[0], 'volume'] = -100
        cleaned = DataProcessor.clean_data(df)
        assert (cleaned['volume'] >= 0).all()

    def test_validate_data_passes_valid(self, sample_ohlcv_df):
        # Should not raise
        DataProcessor.validate_data(sample_ohlcv_df)

    def test_validate_data_fails_missing_column(self, sample_ohlcv_df):
        df = sample_ohlcv_df.drop(columns=['close'])
        with pytest.raises(ValueError, match="Missing required columns"):
            DataProcessor.validate_data(df)

    def test_validate_data_fails_empty(self):
        df = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
        with pytest.raises(ValueError, match="empty"):
            DataProcessor.validate_data(df)

    def test_validate_data_fails_high_less_than_low(self, sample_ohlcv_df):
        df = sample_ohlcv_df.copy()
        df.loc[df.index[0], 'high'] = df.loc[df.index[0], 'low'] - 1
        with pytest.raises(ValueError, match="high < low"):
            DataProcessor.validate_data(df)
