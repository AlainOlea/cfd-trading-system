"""Tests for trading strategy modules."""

import pandas as pd
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

    def test_is_mean_reversion(self):
        assert RSIBBStrategy().mean_reversion is True

    def _touching_lower_bb_df(self, adx_value):
        return pd.DataFrame({
            'close': [100.0] * 5,
            'rsi': [25.0] * 5,       # oversold
            'bb_lower': [101.0] * 5,  # close <= bb_lower -> touch
            'bb_upper': [110.0] * 5,
            'bb_middle': [105.0] * 5,
            'adx': [adx_value] * 5,
        }, index=pd.date_range('2026-01-01', periods=5, freq='1min'))

    def test_require_ranging_suppresses_signal_in_strong_trend(self):
        s = RSIBBStrategy()
        assert s.require_ranging is True
        df = self._touching_lower_bb_df(adx_value=35.0)  # strongly trending
        result = s.generate_signals(df)
        assert (result['signal'] == 'HOLD').all()

    def test_require_ranging_allows_signal_when_ranging(self):
        s = RSIBBStrategy()
        df = self._touching_lower_bb_df(adx_value=10.0)  # ranging
        result = s.generate_signals(df)
        assert (result['signal'] == 'BUY').any()


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


class TestSuperTrendStrategy:
    """Tests for SuperTrend strategy."""

    def test_registered(self):
        assert 'supertrend' in STRATEGY_MAP

    def test_has_required_properties(self):
        from strategies.scalping.supertrend import SuperTrendStrategy
        s = SuperTrendStrategy()
        assert s.name == 'supertrend'
        assert s.timeframe is not None
        assert s.description is not None

    def test_generate_signals_columns(self, df_with_indicators):
        from strategies.scalping.supertrend import SuperTrendStrategy
        result = SuperTrendStrategy().generate_signals(df_with_indicators)
        for col in ['signal', 'entry_price', 'stop_loss', 'take_profit', 'confidence']:
            assert col in result.columns, f"Missing column: {col}"
        assert set(result['signal'].unique()).issubset({'BUY', 'SELL', 'HOLD'})

    def test_sl_on_losing_side(self, df_with_indicators):
        from strategies.scalping.supertrend import SuperTrendStrategy
        result = SuperTrendStrategy().generate_signals(df_with_indicators)
        buys = result[result['signal'] == 'BUY']
        sells = result[result['signal'] == 'SELL']
        assert (buys['stop_loss'] < buys['entry_price']).all()
        assert (buys['take_profit'] > buys['entry_price']).all()
        assert (sells['stop_loss'] > sells['entry_price']).all()
        assert (sells['take_profit'] < sells['entry_price']).all()

    def test_confidence_in_range(self, df_with_indicators):
        from strategies.scalping.supertrend import SuperTrendStrategy
        result = SuperTrendStrategy().generate_signals(df_with_indicators)
        assert (result['confidence'] >= 0).all()
        assert (result['confidence'] <= 1).all()


class TestPivotPointsStrategy:
    """Tests for Pivot Points strategy."""

    def test_registered(self):
        assert 'pivot_points' in STRATEGY_MAP

    def test_has_required_properties(self):
        from strategies.scalping.pivot_points import PivotPointsStrategy
        s = PivotPointsStrategy()
        assert s.name == 'pivot_points'
        assert s.mean_reversion is True   # keeps TimesFM from overwriting SL/TP
        assert s.require_ranging is True

    def test_generate_signals_columns(self, df_with_indicators):
        from strategies.scalping.pivot_points import PivotPointsStrategy
        result = PivotPointsStrategy().generate_signals(df_with_indicators)
        for col in ['signal', 'entry_price', 'stop_loss', 'take_profit', 'confidence']:
            assert col in result.columns, f"Missing column: {col}"
        assert set(result['signal'].unique()).issubset({'BUY', 'SELL', 'HOLD'})

    def test_sl_on_losing_side(self, df_with_indicators):
        from strategies.scalping.pivot_points import PivotPointsStrategy
        result = PivotPointsStrategy().generate_signals(df_with_indicators)
        buys = result[result['signal'] == 'BUY']
        sells = result[result['signal'] == 'SELL']
        assert (buys['stop_loss'] < buys['entry_price']).all()
        assert (buys['take_profit'] > buys['entry_price']).all()
        assert (sells['stop_loss'] > sells['entry_price']).all()
        assert (sells['take_profit'] < sells['entry_price']).all()

    def test_requires_datetime_index(self):
        from strategies.scalping.pivot_points import PivotPointsStrategy
        df = pd.DataFrame({
            'open': [1.0], 'high': [1.0], 'low': [1.0],
            'close': [1.0], 'volume': [1.0],
        })
        with pytest.raises(ValueError, match='DatetimeIndex'):
            PivotPointsStrategy().generate_signals(df)


class TestFibonacciStrategy:
    """Tests for Fibonacci retracement strategy."""

    def test_registered(self):
        assert 'fibonacci' in STRATEGY_MAP

    def test_has_required_properties(self):
        from strategies.swing.fibonacci import FibonacciStrategy
        s = FibonacciStrategy()
        assert s.name == 'fibonacci'
        # ADX gate stays off: it suppresses pullback entries by construction
        # (see class docstring). Trend context = SMA50 + time-ordered impulse.
        assert s.require_trend is False

    def test_generate_signals_columns(self, df_with_indicators):
        from strategies.swing.fibonacci import FibonacciStrategy
        result = FibonacciStrategy().generate_signals(df_with_indicators)
        for col in ['signal', 'entry_price', 'stop_loss', 'take_profit', 'confidence']:
            assert col in result.columns, f"Missing column: {col}"
        assert set(result['signal'].unique()).issubset({'BUY', 'SELL', 'HOLD'})

    def test_sl_on_losing_side(self, df_with_indicators):
        from strategies.swing.fibonacci import FibonacciStrategy
        result = FibonacciStrategy().generate_signals(df_with_indicators)
        buys = result[result['signal'] == 'BUY']
        sells = result[result['signal'] == 'SELL']
        assert (buys['stop_loss'] < buys['entry_price']).all()
        assert (buys['take_profit'] > buys['entry_price']).all()
        assert (sells['stop_loss'] > sells['entry_price']).all()
        assert (sells['take_profit'] < sells['entry_price']).all()

    def test_short_df_returns_hold(self, df_with_indicators):
        from strategies.swing.fibonacci import FibonacciStrategy
        short = df_with_indicators.head(10)
        result = FibonacciStrategy().generate_signals(short)
        assert (result['signal'] == 'HOLD').all()
