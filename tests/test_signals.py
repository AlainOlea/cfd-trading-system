"""Tests for signal generator and manager modules."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from signals.generator import Signal, SignalGenerator
from signals.manager import SignalManager


class TestSignal:
    """Tests for Signal dataclass."""

    def test_signal_creation(self):
        s = Signal(
            strategy='macd_vwap', ticker='SPY', interval='1d',
            direction='BUY', entry_price=100.0,
            stop_loss=99.5, take_profit=101.0, confidence=0.8,
        )
        assert s.direction == 'BUY'
        assert s.entry_price == 100.0

    def test_risk_reward_ratio_buy(self):
        s = Signal(
            strategy='test', ticker='SPY', interval='1d',
            direction='BUY', entry_price=100.0,
            stop_loss=99.0, take_profit=103.0, confidence=0.7,
        )
        assert s.risk_reward_ratio == 3.0  # 3:1 reward:risk

    def test_risk_reward_ratio_hold(self):
        s = Signal(
            strategy='test', ticker='SPY', interval='1d',
            direction='HOLD', entry_price=100.0,
            stop_loss=0, take_profit=0, confidence=0,
        )
        assert s.risk_reward_ratio is None

    def test_to_dict(self):
        s = Signal(
            strategy='macd_vwap', ticker='SPY', interval='1d',
            direction='BUY', entry_price=100.0,
            stop_loss=99.5, take_profit=101.0, confidence=0.8,
        )
        d = s.to_dict()
        assert d['strategy'] == 'macd_vwap'
        assert d['direction'] == 'BUY'
        assert 'timestamp' in d


class TestSignalManager:
    """Tests for SignalManager."""

    def test_log_and_retrieve(self):
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
            log_path = Path(f.name)

        try:
            manager = SignalManager(log_file=log_path)
            signal = Signal(
                strategy='macd_vwap', ticker='SPY', interval='1d',
                direction='BUY', entry_price=100.0,
                stop_loss=99.5, take_profit=101.0, confidence=0.8,
            )
            manager.log_signal(signal)

            history = manager.get_history()
            assert len(history) == 1
            assert history.iloc[0]['ticker'] == 'SPY'
        finally:
            log_path.unlink(missing_ok=True)

    def test_format_signal_buy(self):
        s = Signal(
            strategy='macd_vwap', ticker='SPY', interval='1d',
            direction='BUY', entry_price=100.0,
            stop_loss=99.5, take_profit=101.0, confidence=0.8,
        )
        text = SignalManager.format_signal(s)
        assert 'BUY' in text
        assert 'SPY' in text
        assert '100.00' in text

    def test_format_signal_hold(self):
        s = Signal(
            strategy='macd_vwap', ticker='SPY', interval='1d',
            direction='HOLD', entry_price=100.0,
            stop_loss=0, take_profit=0, confidence=0,
        )
        text = SignalManager.format_signal(s)
        assert 'HOLD' in text

    def test_filter_by_ticker(self):
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
            log_path = Path(f.name)

        try:
            manager = SignalManager(log_file=log_path)
            signals = [
                Signal(strategy='test', ticker='SPY', interval='1d',
                       direction='HOLD', entry_price=100.0,
                       stop_loss=0, take_profit=0, confidence=0),
                Signal(strategy='test', ticker='GLD', interval='1d',
                       direction='HOLD', entry_price=100.0,
                       stop_loss=0, take_profit=0, confidence=0),
                Signal(strategy='test', ticker='SPY', interval='1d',
                       direction='BUY', entry_price=100.0,
                       stop_loss=99.0, take_profit=101.0, confidence=0.8),
            ]
            for sig in signals:
                manager.log_signal(sig)

            spy_signals = manager.get_history(ticker='SPY')
            assert len(spy_signals) == 2
        finally:
            log_path.unlink(missing_ok=True)
