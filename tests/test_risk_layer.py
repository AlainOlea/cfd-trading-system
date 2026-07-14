"""Tests for risk layer, signal dedup, Telegram dry-run, and ML metrics."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pandas as pd
import pytest

from signals.alpaca_broker import AlpacaBroker, _is_crypto, _is_stock
from signals.telegram_bot import TelegramNotifier
from signals.generator import Signal
from signals.pipeline import PipelineResult, UnifiedPipeline
from signals.manager import SignalManager


# ─── Risk Layer Tests ────────────────────────────────────────────────


class TestDrawdownCheck:
    """Tests for session drawdown kill-switch."""

    def test_no_drawdown_on_first_call(self):
        broker = AlpacaBroker()
        broker._session_high_equity = 0
        result = broker._check_drawdown(100000)
        assert result is None
        assert broker._session_high_equity == 100000

    def test_new_high_resets_tracking(self):
        broker = AlpacaBroker()
        broker._session_high_equity = 95000
        result = broker._check_drawdown(100000)
        assert result is None
        assert broker._session_high_equity == 100000

    def test_warning_at_5pct(self):
        broker = AlpacaBroker()
        broker._session_high_equity = 100000
        # Warning logs but does NOT block (returns None)
        result = broker._check_drawdown(94000)
        assert result is None
        assert broker._halted is False

    def test_halt_at_10pct(self):
        broker = AlpacaBroker()
        broker._session_high_equity = 100000
        result = broker._check_drawdown(89000)
        assert result is not None
        assert "HALT" in result
        assert broker._halted is True

    def test_no_halt_under_5pct(self):
        broker = AlpacaBroker()
        broker._session_high_equity = 100000
        result = broker._check_drawdown(96000)
        assert result is None
        assert broker._halted is False

    def test_halt_persists(self):
        broker = AlpacaBroker()
        broker._session_high_equity = 100000
        broker._halted = True
        # Even at 1% drawdown, _halted stays True
        result = broker._check_drawdown(99000)
        assert broker._halted is True


class TestPortfolioRiskChecks:
    """Tests for aggregate exposure, per-name, and position count limits."""

    def _make_broker_with_positions(self, positions: dict):
        """Create a broker with mocked positions."""
        broker = AlpacaBroker()
        broker.get_open_positions = MagicMock(return_value=positions)
        broker._session_high_equity = 100000
        return broker

    def test_max_concurrent_positions(self):
        # MAX_CONCURRENT_POSITIONS = 10 in settings.py
        tickers = ['SPY', 'QQQ', 'AAPL', 'DIA', 'GLD', 'SLV', 'USO', 'UNG', 'NVDA', 'MSFT']
        positions = {t: {'market_value': 5000} for t in tickers}
        broker = self._make_broker_with_positions(positions)
        result = broker._check_portfolio_risk('AMZN', 5000, 100000)
        assert result is not None
        assert "MAX POSITIONS" in result

    def test_max_concurrent_not_reached(self):
        positions = {
            'SPY': {'market_value': 5000},
            'QQQ': {'market_value': 5000},
        }
        broker = self._make_broker_with_positions(positions)
        result = broker._check_portfolio_risk('AAPL', 5000, 100000)
        assert result is None

    def test_gross_exposure_exceeded(self):
        positions = {
            'SPY': {'market_value': 15000},
            'QQQ': {'market_value': 10000},
        }
        broker = self._make_broker_with_positions(positions)
        result = broker._check_portfolio_risk('AAPL', 10000, 100000)
        assert result is not None
        assert "GROSS EXPOSURE" in result

    def test_gross_exposure_within_limit(self):
        positions = {
            'SPY': {'market_value': 10000},
        }
        broker = self._make_broker_with_positions(positions)
        result = broker._check_portfolio_risk('QQQ', 5000, 100000)
        assert result is None

    def test_per_name_exposure_exceeded(self):
        positions = {
            'SPY': {'market_value': 8000},
        }
        broker = self._make_broker_with_positions(positions)
        result = broker._check_portfolio_risk('SPY', 3000, 100000)
        assert result is not None
        assert "NAME EXPOSURE" in result

    def test_crypto_aggregate_exceeded(self):
        positions = {
            'BTC/USD': {'market_value': 5000},
            'ETH/USD': {'market_value': 4000},
        }
        broker = self._make_broker_with_positions(positions)
        result = broker._check_portfolio_risk('SOL/USD', 2000, 100000)
        assert result is not None
        assert "CRYPTO EXPOSURE" in result

    def test_per_name_exposure_counts_existing_crypto_position(self):
        """Alpaca's positions endpoint returns crypto symbols with no
        separator ('SOLUSD'), while place_signal() checks with the slash
        format ('SOL/USD'). If the lookup doesn't normalize, an existing
        $9000 position is invisible and a second buy that would push
        total exposure to 9.5% (over the 3% crypto cap) gets allowed.
        """
        positions = {
            'SOLUSD': {'market_value': 9000},
        }
        broker = self._make_broker_with_positions(positions)
        result = broker._check_portfolio_risk('SOL/USD', 500, 100000)
        assert result is not None
        assert "NAME EXPOSURE" in result


class TestPositionSizing:
    """Tests for dynamic position sizing."""

    def test_sizing_uses_equity_not_cash(self):
        broker = AlpacaBroker()
        broker.get_account_summary = MagicMock(return_value={
            'cash': 50000, 'equity': 100000, 'buying_power': 200000,
        })
        shares = broker.calculate_shares(
            entry_price=100, stop_loss=99.5, equity=100000, is_crypto=False,
        )
        # risk_capital = 100000 * 0.02 = 2000
        # shares_by_risk = 2000 / 0.5 = 4000
        # shares_by_capital = (100000 * 0.05) / 100 = 50
        assert shares == 50.0

    def test_crypto_tighter_limits(self):
        broker = AlpacaBroker()
        shares_stock = broker.calculate_shares(
            entry_price=100, stop_loss=99.5, equity=100000, is_crypto=False,
        )
        shares_crypto = broker.calculate_shares(
            entry_price=100, stop_loss=99.5, equity=100000, is_crypto=True,
        )
        # Crypto: 3% cap vs 5% for stocks
        assert shares_crypto < shares_stock

    def test_zero_risk_per_share(self):
        broker = AlpacaBroker()
        shares = broker.calculate_shares(
            entry_price=100, stop_loss=100, equity=100000,
        )
        assert shares == 0.0


# ─── Signal Dedup Tests ─────────────────────────────────────────────


class TestBrokerDedup:
    """Tests for broker-level signal deduplication."""

    def test_dedup_skips_duplicate_signal(self):
        broker = AlpacaBroker()
        mock_trading = MagicMock()
        # Mock open orders with a matching order
        mock_order = MagicMock()
        mock_order.symbol = 'SPY'
        mock_trading.get_orders = MagicMock(return_value=[mock_order])
        broker._trading = mock_trading

        result = broker._was_recently_attempted('SPY', 'BUY', hours=4)
        assert result is True

    def test_dedup_allows_new_signal(self):
        broker = AlpacaBroker()
        mock_trading = MagicMock()
        mock_trading.get_orders = MagicMock(return_value=[])
        broker._trading = mock_trading

        result = broker._was_recently_attempted('SPY', 'BUY', hours=4)
        assert result is False

    def test_dedup_different_ticker(self):
        broker = AlpacaBroker()
        mock_trading = MagicMock()
        mock_order = MagicMock()
        mock_order.symbol = 'QQQ'
        mock_trading.get_orders = MagicMock(return_value=[mock_order])
        broker._trading = mock_trading

        result = broker._was_recently_attempted('SPY', 'BUY', hours=4)
        assert result is False

    def test_dedup_different_direction(self):
        broker = AlpacaBroker()
        mock_trading = MagicMock()
        # Open buy order exists for SPY — blocks ALL directions for SPY
        mock_order = MagicMock()
        mock_order.symbol = 'SPY'
        mock_order.side.value = 'buy'
        mock_trading.get_orders = MagicMock(return_value=[mock_order])
        broker._trading = mock_trading

        # SELL should also be blocked when there's an open BUY
        result = broker._was_recently_attempted('SPY', 'SELL', hours=4)
        assert result is True

    def test_dedup_allows_new_direction_when_no_open_orders(self):
        broker = AlpacaBroker()
        mock_trading = MagicMock()
        # No open orders, but recent closed SELL for SPY
        from datetime import datetime
        mock_closed = MagicMock()
        mock_closed.symbol = 'SPY'
        mock_closed.side.value = 'sell'
        mock_closed.filled_at = datetime.now()
        mock_trading.get_orders = MagicMock(return_value=[])
        broker._trading = mock_trading

        # BUY should be allowed (different direction, no open orders)
        result = broker._was_recently_attempted('SPY', 'BUY', hours=4)
        assert result is False


class TestCryptoSymbolFormats:
    """Alpaca is inconsistent about crypto symbol formats across endpoints:
    positions come back as 'SOLUSD' (no separator), orders as 'SOL/USD'
    (slash), and our internal ticker format is 'SOL-USD' (hyphen). Every
    lookup that compares across these must normalize, or it silently
    never matches.
    """

    def test_has_position_matches_noslash_alpaca_format(self):
        broker = AlpacaBroker()
        broker.get_open_positions = MagicMock(return_value={'SOLUSD': {}})
        # place_signal() calls has_position() with the slash format
        assert broker.has_position('SOL/USD') is True

    def test_has_position_no_match_when_absent(self):
        broker = AlpacaBroker()
        broker.get_open_positions = MagicMock(return_value={'AAPL': {}})
        assert broker.has_position('SOL/USD') is False

    def test_dedup_matches_crypto_across_formats(self):
        broker = AlpacaBroker()
        mock_trading = MagicMock()
        mock_order = MagicMock()
        # Alpaca's order symbol comes back with a slash
        mock_order.symbol = 'SOL/USD'
        mock_trading.get_orders = MagicMock(return_value=[mock_order])
        broker._trading = mock_trading

        # place_signal() calls _was_recently_attempted() with our hyphen ticker
        result = broker._was_recently_attempted('SOL-USD', 'BUY', hours=4)
        assert result is True


class TestTelegramDedup:
    """Tests for Telegram notification deduplication."""

    def test_dedup_prevents_duplicate_notification(self):
        pipeline = UnifiedPipeline.__new__(UnifiedPipeline)
        pipeline.send_telegram = True
        pipeline.notifier = MagicMock()
        pipeline.notifier.is_configured = True
        pipeline.notifier.send_alert = MagicMock(return_value=True)
        pipeline._dedup_file = Path(tempfile.mktemp(suffix='.txt'))

        result = MagicMock()
        result.is_actionable = MagicMock(return_value=True)
        result.ticker = 'SPY'
        result.final_direction = 'BUY'
        result.signal = MagicMock()
        result.signal.direction = 'BUY'

        # First call should send
        pipeline.format_telegram_message = MagicMock(return_value="test msg")
        sent = pipeline.notify_actionable([result])
        assert sent == 1

        # Second call should skip (dedup from file)
        sent = pipeline.notify_actionable([result])
        assert sent == 0

        # Cleanup
        pipeline._dedup_file.unlink(missing_ok=True)

    def test_dedup_allows_different_ticker(self):
        pipeline = UnifiedPipeline.__new__(UnifiedPipeline)
        pipeline.send_telegram = True
        pipeline.notifier = MagicMock()
        pipeline.notifier.is_configured = True
        pipeline.notifier.send_alert = MagicMock(return_value=True)
        pipeline._dedup_file = Path(tempfile.mktemp(suffix='.txt'))

        result1 = MagicMock()
        result1.is_actionable = MagicMock(return_value=True)
        result1.ticker = 'SPY'
        result1.final_direction = 'BUY'
        result1.signal = MagicMock()
        result1.signal.direction = 'BUY'

        result2 = MagicMock()
        result2.is_actionable = MagicMock(return_value=True)
        result2.ticker = 'QQQ'
        result2.final_direction = 'BUY'
        result2.signal = MagicMock()
        result2.signal.direction = 'BUY'

        pipeline.format_telegram_message = MagicMock(return_value="test msg")

        sent = pipeline.notify_actionable([result1, result2])
        assert sent == 2

        pipeline._dedup_file.unlink(missing_ok=True)

    def test_dedup_allows_different_direction(self):
        pipeline = UnifiedPipeline.__new__(UnifiedPipeline)
        pipeline.send_telegram = True
        pipeline.notifier = MagicMock()
        pipeline.notifier.is_configured = True
        pipeline.notifier.send_alert = MagicMock(return_value=True)
        pipeline._dedup_file = Path(tempfile.mktemp(suffix='.txt'))

        result1 = MagicMock()
        result1.is_actionable = MagicMock(return_value=True)
        result1.ticker = 'SPY'
        result1.final_direction = 'BUY'
        result1.signal = MagicMock()
        result1.signal.direction = 'BUY'

        result2 = MagicMock()
        result2.is_actionable = MagicMock(return_value=True)
        result2.ticker = 'SPY'
        result2.final_direction = 'SELL'
        result2.signal = MagicMock()
        result2.signal.direction = 'SELL'

        pipeline.format_telegram_message = MagicMock(return_value="test msg")

        sent = pipeline.notify_actionable([result1, result2])
        assert sent == 2

        pipeline._dedup_file.unlink(missing_ok=True)

    def test_dedup_persists_across_instances(self):
        """Verify dedup works across separate pipeline instances (simulates hourly runs)."""
        dedup_path = Path(tempfile.mktemp(suffix='.txt'))

        # First pipeline instance
        p1 = UnifiedPipeline.__new__(UnifiedPipeline)
        p1.send_telegram = True
        p1.notifier = MagicMock()
        p1.notifier.is_configured = True
        p1.notifier.send_alert = MagicMock(return_value=True)
        p1._dedup_file = dedup_path

        result = MagicMock()
        result.is_actionable = MagicMock(return_value=True)
        result.ticker = 'SPY'
        result.final_direction = 'BUY'
        result.signal = MagicMock()
        result.signal.direction = 'BUY'

        p1.format_telegram_message = MagicMock(return_value="test msg")
        sent = p1.notify_actionable([result])
        assert sent == 1

        # Second pipeline instance (simulates next hour's run)
        p2 = UnifiedPipeline.__new__(UnifiedPipeline)
        p2.send_telegram = True
        p2.notifier = MagicMock()
        p2.notifier.is_configured = True
        p2.notifier.send_alert = MagicMock(return_value=True)
        p2._dedup_file = dedup_path

        sent = p2.notify_actionable([result])
        assert sent == 0  # Should be deduped

        dedup_path.unlink(missing_ok=True)


# ─── Telegram Dry-Run Tests ─────────────────────────────────────────


class TestTelegramDryRun:
    """Tests for Telegram notifier dry-run mode."""

    def test_disabled_returns_false(self):
        notifier = TelegramNotifier(enabled=False)
        result = notifier.send_alert("test message")
        assert result is False

    def test_not_configured_returns_false(self):
        notifier = TelegramNotifier(bot_token="", chat_id="", enabled=True)
        result = notifier.send_alert("test message")
        assert result is False

    def test_format_signal_buy(self):
        s = Signal(
            strategy='macd_vwap', ticker='SPY', interval='1h',
            direction='BUY', entry_price=100.0,
            stop_loss=99.5, take_profit=101.0, confidence=0.8,
        )
        msg = TelegramNotifier._format_signal_message(s)
        assert 'BUY' in msg
        assert 'SPY' in msg
        assert '100.00' in msg
        assert '99.50' in msg
        assert '101.00' in msg

    def test_format_signal_hold(self):
        s = Signal(
            strategy='macd_vwap', ticker='SPY', interval='1h',
            direction='HOLD', entry_price=100.0,
            stop_loss=0, take_profit=0, confidence=0,
        )
        msg = TelegramNotifier._format_signal_message(s)
        assert 'HOLD' in msg
        assert 'No action' in msg

    def test_format_signal_sell(self):
        s = Signal(
            strategy='rsi_bb', ticker='QQQ', interval='1d',
            direction='SELL', entry_price=500.0,
            stop_loss=505.0, take_profit=490.0, confidence=0.7,
        )
        msg = TelegramNotifier._format_signal_message(s)
        assert 'SELL' in msg
        assert 'QQQ' in msg


# ─── Per-Class ML Metrics Tests ─────────────────────────────────────


class TestPerClassMLMetrics:
    """Tests for XGBoost per-class evaluation metrics."""

    def test_per_class_metrics_structure(self):
        """Verify per-class metrics have correct structure."""
        from models.xgboost_model import XGBoostTrader

        trader = XGBoostTrader()
        trader.model = MagicMock()
        trader.scaler = MagicMock()

        # Mock predictions: 3-class (0=bearish, 1=neutral, 2=bullish)
        y_test = np.array([0, 0, 0, 1, 1, 1, 1, 2, 2, 2])
        y_pred = np.array([0, 0, 1, 1, 1, 2, 0, 2, 2, 1])

        trader.model.predict = MagicMock(return_value=y_pred)

        metrics = trader.evaluate(np.zeros((10, 5)), y_test)

        assert 'per_class' in metrics
        assert 'bearish' in metrics['per_class']
        assert 'neutral' in metrics['per_class']
        assert 'bullish' in metrics['per_class']

        for cls_name in ['bearish', 'neutral', 'bullish']:
            cls_metrics = metrics['per_class'][cls_name]
            assert 'precision' in cls_metrics
            assert 'recall' in cls_metrics
            assert 'f1' in cls_metrics
            assert 'support' in cls_metrics

    def test_confusion_matrix_structure(self):
        """Verify confusion matrix has correct structure."""
        from models.xgboost_model import XGBoostTrader

        trader = XGBoostTrader()
        trader.model = MagicMock()
        trader.scaler = MagicMock()

        y_test = np.array([0, 0, 1, 1, 2, 2])
        y_pred = np.array([0, 1, 1, 1, 2, 0])

        trader.model.predict = MagicMock(return_value=y_pred)
        metrics = trader.evaluate(np.zeros((6, 5)), y_test)

        assert 'confusion_matrix' in metrics
        cm = metrics['confusion_matrix']
        assert 'bearish' in cm
        assert 'neutral' in cm
        assert 'bullish' in cm
        # Diagonal should match
        assert cm['bearish']['bearish'] == 1
        assert cm['neutral']['neutral'] == 2
        assert cm['bullish']['bullish'] == 1

    def test_class_distribution(self):
        """Verify class distribution is computed."""
        from models.xgboost_model import XGBoostTrader

        trader = XGBoostTrader()
        trader.model = MagicMock()
        trader.scaler = MagicMock()

        y_test = np.array([0, 0, 0, 1, 2])  # 60% bearish
        y_pred = np.array([0, 0, 1, 1, 2])

        trader.model.predict = MagicMock(return_value=y_pred)
        metrics = trader.evaluate(np.zeros((5, 5)), y_test)

        assert 'class_distribution' in metrics
        dist = metrics['class_distribution']
        assert abs(dist['bearish'] - 0.6) < 0.01
        assert abs(dist['neutral'] - 0.2) < 0.01
        assert abs(dist['bullish'] - 0.2) < 0.01

    def test_dominant_class_accuracy(self):
        """Verify dominant class baseline is reported."""
        from models.xgboost_model import XGBoostTrader

        trader = XGBoostTrader()
        trader.model = MagicMock()
        trader.scaler = MagicMock()

        y_test = np.array([1, 1, 1, 1, 1, 2])  # 83% neutral
        y_pred = np.array([1, 1, 1, 1, 1, 1])  # All predict neutral

        trader.model.predict = MagicMock(return_value=y_pred)
        metrics = trader.evaluate(np.zeros((6, 5)), y_test)

        assert 'dominant_class_accuracy' in metrics
        assert metrics['dominant_class_accuracy'] == pytest.approx(0.8333, abs=0.01)

    def test_perfect_predictions(self):
        """Verify metrics with perfect predictions."""
        from models.xgboost_model import XGBoostTrader

        trader = XGBoostTrader()
        trader.model = MagicMock()
        trader.scaler = MagicMock()

        y_test = np.array([0, 0, 1, 1, 2, 2])
        y_pred = np.array([0, 0, 1, 1, 2, 2])

        trader.model.predict = MagicMock(return_value=y_pred)
        metrics = trader.evaluate(np.zeros((6, 5)), y_test)

        assert metrics['accuracy'] == 1.0
        for cls_name in ['bearish', 'neutral', 'bullish']:
            assert metrics['per_class'][cls_name]['f1'] == 1.0


# ─── TimesFM Strategy-Aware SL/TP ──────────────────────────────────


class TestTimesFMStrategyAware:
    """TimesFM's momentum-forecast SL/TP must not overwrite a mean-reversion
    strategy's own exit thesis (e.g. rsi_bb targeting bb_middle) — but the
    confluence bonus is strategy-agnostic and should still apply.
    """

    def _make_result(self, strategy, direction, ticker='GLD', interval='1h'):
        sig = Signal(
            strategy=strategy, ticker=ticker, interval=interval,
            direction=direction, entry_price=100.0,
            stop_loss=99.3, take_profit=97.0, confidence=0.6,
        )
        return PipelineResult(
            ticker=ticker, interval=interval, technical_signal=sig,
            final_direction=direction, final_confidence=0.6,
            confluence_score=3,
        )

    def _pipeline(self, ticker='GLD', direction=-1):
        p = UnifiedPipeline.__new__(UnifiedPipeline)
        p.timesfm = MagicMock(SUPPORTED_INTERVALS=frozenset({'1m', '1h'}))
        p._tfm_results = {ticker: {'direction': direction, 'quantiles': None, 'last_price': 100.0}}
        return p

    def test_mean_reversion_strategy_keeps_its_own_sl_tp(self):
        p = self._pipeline()
        result = self._make_result('rsi_bb', 'SELL')
        p._apply_timesfm([result])
        assert result.technical_signal.stop_loss == 99.3
        assert result.technical_signal.take_profit == 97.0

    def test_momentum_strategy_sl_tp_overwritten_by_fallback(self):
        from config.settings import SCALPING_SL_PERCENT, SCALPING_TP_PERCENT

        p = self._pipeline()
        result = self._make_result('macd_vwap', 'SELL')
        p._apply_timesfm([result])
        expected_sl = 100.0 * (1 + SCALPING_SL_PERCENT)
        expected_tp = 100.0 * (1 - SCALPING_TP_PERCENT)
        assert result.technical_signal.stop_loss == pytest.approx(expected_sl)
        assert result.technical_signal.take_profit == pytest.approx(expected_tp)

    def test_confluence_bonus_still_applies_to_mean_reversion(self):
        p = self._pipeline()
        result = self._make_result('rsi_bb', 'SELL')
        p._apply_timesfm([result])
        assert result.confluence_score == 4  # TimesFM direction agrees -> +1


# ─── Integration Tests ──────────────────────────────────────────────


class TestRiskLayerIntegration:
    """Integration tests for the full risk layer in place_signal."""

    def test_hold_signal_bypasses_risk_checks(self):
        broker = AlpacaBroker()
        broker._session_high_equity = 100000

        signal = Signal(
            strategy='macd_vwap', ticker='SPY', interval='1h',
            direction='HOLD', entry_price=100.0,
            stop_loss=0, take_profit=0, confidence=0,
        )
        result = broker.place_signal(signal)
        assert result.placed is False
        assert "HOLD" in result.reason

    def test_unsupported_ticker_rejected(self):
        broker = AlpacaBroker()
        broker._session_high_equity = 100000

        signal = Signal(
            strategy='macd_vwap', ticker='INVALID', interval='1h',
            direction='BUY', entry_price=100.0,
            stop_loss=99.5, take_profit=101.0, confidence=0.8,
        )
        result = broker.place_signal(signal)
        assert result.placed is False
        assert "not supported" in result.reason

    def test_invalid_sl_tp_rejected(self):
        broker = AlpacaBroker()
        broker._session_high_equity = 100000

        signal = Signal(
            strategy='macd_vwap', ticker='SPY', interval='1h',
            direction='BUY', entry_price=100.0,
            stop_loss=0, take_profit=0, confidence=0.8,
        )
        result = broker.place_signal(signal)
        assert result.placed is False
        assert "Invalid SL/TP" in result.reason
