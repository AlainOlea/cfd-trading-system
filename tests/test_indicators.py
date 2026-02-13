"""Tests for technical indicators module."""

import pytest

from indicators.technical import TechnicalIndicators


class TestTechnicalIndicators:
    """Tests for TechnicalIndicators."""

    def test_add_all_indicators_adds_columns(self, large_ohlcv_df):
        df = TechnicalIndicators.add_all_indicators(large_ohlcv_df)
        expected_cols = [
            'macd', 'macd_signal', 'macd_histogram',
            'rsi',
            'bb_upper', 'bb_middle', 'bb_lower',
            'sma_50', 'sma_200',
            'ema_50', 'ema_200',
            'stoch_k', 'stoch_d',
            'adx',
            'atr',
            'obv',
        ]
        for col in expected_cols:
            assert col in df.columns, f"Missing column: {col}"

    def test_add_all_preserves_ohlcv(self, large_ohlcv_df):
        df = TechnicalIndicators.add_all_indicators(large_ohlcv_df)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            assert col in df.columns

    def test_rsi_in_range(self, large_ohlcv_df):
        df = TechnicalIndicators.add_rsi(large_ohlcv_df.copy())
        rsi = df['rsi'].dropna()
        assert (rsi >= 0).all() and (rsi <= 100).all()

    def test_macd_columns(self, large_ohlcv_df):
        df = TechnicalIndicators.add_macd(large_ohlcv_df.copy())
        assert 'macd' in df.columns
        assert 'macd_signal' in df.columns
        assert 'macd_histogram' in df.columns

    def test_bollinger_bands_order(self, large_ohlcv_df):
        df = TechnicalIndicators.add_bollinger_bands(large_ohlcv_df.copy())
        valid = df.dropna(subset=['bb_upper', 'bb_middle', 'bb_lower'])
        assert (valid['bb_upper'] >= valid['bb_middle']).all()
        assert (valid['bb_middle'] >= valid['bb_lower']).all()

    def test_sma_length(self, large_ohlcv_df):
        df = TechnicalIndicators.add_sma(large_ohlcv_df.copy(), period=50)
        # SMA should have NaN for first (period-1) values
        assert df['sma_50'].isna().sum() >= 49

    def test_atr_positive(self, large_ohlcv_df):
        df = TechnicalIndicators.add_atr(large_ohlcv_df.copy())
        atr = df['atr'].dropna()
        assert (atr >= 0).all()

    def test_obv_exists(self, large_ohlcv_df):
        df = TechnicalIndicators.add_obv(large_ohlcv_df.copy())
        assert 'obv' in df.columns
        assert df['obv'].isna().sum() <= 1  # First row has no previous close
