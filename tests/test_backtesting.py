"""Tests for backtesting engine and metrics modules."""

import pytest

from backtesting.engine import BacktestEngine, BacktestResult
from backtesting.metrics import PerformanceMetrics, _safe_float
from strategies.scalping.macd_vwap import MACDVWAPStrategy


class TestBacktestEngine:
    """Tests for BacktestEngine."""

    def test_run_returns_result(self, df_with_indicators):
        engine = BacktestEngine(initial_capital=10000)
        strategy = MACDVWAPStrategy()
        result = engine.run(strategy, df_with_indicators, ticker='TEST', interval='1d')
        assert isinstance(result, BacktestResult)
        assert result.strategy_name == 'macd_vwap'
        assert result.ticker == 'TEST'
        assert result.interval == '1d'
        assert result.initial_capital == 10000

    def test_result_has_portfolio(self, df_with_indicators):
        engine = BacktestEngine()
        strategy = MACDVWAPStrategy()
        result = engine.run(strategy, df_with_indicators)
        assert result.portfolio is not None

    def test_result_has_signals_df(self, df_with_indicators):
        engine = BacktestEngine()
        strategy = MACDVWAPStrategy()
        result = engine.run(strategy, df_with_indicators)
        assert 'signal' in result.signals_df.columns


class TestPerformanceMetrics:
    """Tests for PerformanceMetrics."""

    def test_calculate_all_returns_dict(self, df_with_indicators):
        engine = BacktestEngine()
        strategy = MACDVWAPStrategy()
        result = engine.run(strategy, df_with_indicators)
        metrics = PerformanceMetrics.calculate_all(result)
        assert isinstance(metrics, dict)
        assert 'total_return_pct' in metrics
        assert 'total_trades' in metrics
        assert 'sharpe_ratio' in metrics

    def test_format_summary_returns_string(self, df_with_indicators):
        engine = BacktestEngine()
        strategy = MACDVWAPStrategy()
        result = engine.run(strategy, df_with_indicators)
        metrics = PerformanceMetrics.calculate_all(result)
        summary = PerformanceMetrics.format_summary(metrics)
        assert isinstance(summary, str)
        assert 'BACKTEST RESULTS' in summary


class TestSafeFloat:
    """Tests for _safe_float helper."""

    def test_normal_float(self):
        assert _safe_float(3.14) == 3.14

    def test_nan(self):
        assert _safe_float(float('nan')) == 0.0

    def test_inf(self):
        assert _safe_float(float('inf')) == 0.0

    def test_neg_inf(self):
        assert _safe_float(float('-inf')) == 0.0

    def test_custom_default(self):
        assert _safe_float(float('nan'), default=-1.0) == -1.0

    def test_none(self):
        assert _safe_float(None) == 0.0
