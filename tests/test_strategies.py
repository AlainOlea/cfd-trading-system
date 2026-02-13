"""Tests for trading strategy modules."""

import pytest

from strategies import STRATEGY_MAP
from strategies.base import BaseStrategy
from strategies.scalping.macd_vwap import MACDVWAPStrategy
from strategies.scalping.rsi_bb import RSIBBStrategy
from strategies.swing.ma_crossover import MACrossoverStrategy


class TestStrategyMap:
    """Tests for strategy registration."""

    def test_all_strategies_registered(self):
        assert 'macd_vwap' in STRATEGY_MAP
        assert 'rsi_bb' in STRATEGY_MAP
        assert 'ma_crossover' in STRATEGY_MAP

    def test_strategies_are_classes(self):
        for name, cls in STRATEGY_MAP.items():
            assert issubclass(cls, BaseStrategy), f"{name} is not a BaseStrategy subclass"


class TestMACDVWAPStrategy:
    """Tests for MACD+VWAP strategy."""

    def test_has_required_properties(self):
        s = MACDVWAPStrategy()
        assert s.name == 'macd_vwap'
        assert s.timeframe is not None
        assert s.description is not None

    def test_generate_signals_columns(self, df_with_indicators):
        s = MACDVWAPStrategy()
        result = s.generate_signals(df_with_indicators)
        for col in ['signal', 'entry_price', 'stop_loss', 'take_profit', 'confidence']:
            assert col in result.columns, f"Missing column: {col}"

    def test_signals_are_valid_values(self, df_with_indicators):
        s = MACDVWAPStrategy()
        result = s.generate_signals(df_with_indicators)
        valid_signals = {'BUY', 'SELL', 'HOLD'}
        assert set(result['signal'].unique()).issubset(valid_signals)

    def test_confidence_in_range(self, df_with_indicators):
        s = MACDVWAPStrategy()
        result = s.generate_signals(df_with_indicators)
        assert (result['confidence'] >= 0).all()
        assert (result['confidence'] <= 1).all()


class TestRSIBBStrategy:
    """Tests for RSI+BB strategy."""

    def test_has_required_properties(self):
        s = RSIBBStrategy()
        assert s.name == 'rsi_bb'

    def test_generate_signals_columns(self, df_with_indicators):
        s = RSIBBStrategy()
        result = s.generate_signals(df_with_indicators)
        for col in ['signal', 'entry_price', 'stop_loss', 'take_profit', 'confidence']:
            assert col in result.columns

    def test_signals_are_valid_values(self, df_with_indicators):
        s = RSIBBStrategy()
        result = s.generate_signals(df_with_indicators)
        valid_signals = {'BUY', 'SELL', 'HOLD'}
        assert set(result['signal'].unique()).issubset(valid_signals)


class TestMACrossoverStrategy:
    """Tests for MA Crossover strategy."""

    def test_has_required_properties(self):
        s = MACrossoverStrategy()
        assert s.name == 'ma_crossover'

    def test_generate_signals_columns(self, df_with_indicators):
        s = MACrossoverStrategy()
        result = s.generate_signals(df_with_indicators)
        for col in ['signal', 'entry_price', 'stop_loss', 'take_profit', 'confidence']:
            assert col in result.columns


class TestPositionSizing:
    """Tests for position sizing calculation."""

    def test_position_size_calculation(self):
        size = BaseStrategy.calculate_position_size(
            capital=10000, risk_per_trade=0.02, stop_loss_pct=0.005,
        )
        # With 2% risk on 10k and 0.5% SL: 200 / 0.005 = 40000 units
        assert size == 40000

    def test_position_size_zero_sl(self):
        size = BaseStrategy.calculate_position_size(
            capital=10000, risk_per_trade=0.02, stop_loss_pct=0,
        )
        assert size == 0
