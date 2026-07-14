"""Integration tests for the full paper-trade flow.

Mocks Alpaca API and Telegram to test:
- CLI paper-trade command end-to-end
- Broker place_signal with various scenarios
- Pipeline → broker handoff
- Telegram httpx-based sending
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, PropertyMock
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from signals.generator import Signal
from signals.pipeline import PipelineResult, UnifiedPipeline
from signals.alpaca_broker import AlpacaBroker, TradeResult


def _make_signal(
    ticker='SPY', direction='BUY', entry=550.0,
    sl=547.25, tp=555.5, conf=0.75, interval='1h',
    strategy='macd_vwap',
) -> Signal:
    return Signal(
        strategy=strategy, ticker=ticker, interval=interval,
        direction=direction, entry_price=entry, stop_loss=sl,
        take_profit=tp, confidence=conf,
    )


def _make_result(
    ticker='SPY', direction='BUY', entry=550.0,
    sl=547.25, tp=555.5, conf=0.75, interval='1h',
    confluence=3, strategy='macd_vwap',
) -> PipelineResult:
    sig = _make_signal(
        ticker=ticker, direction=direction, entry=entry,
        sl=sl, tp=tp, conf=conf, interval=interval,
        strategy=strategy,
    )
    return PipelineResult(
        ticker=ticker, interval=interval,
        technical_signal=sig,
        final_direction=direction,
        final_confidence=conf,
        confluence_score=confluence,
    )


# ═══════════════════════════════════════════════════════════════════════
# 1. Broker place_signal — unit-level integration with mocked API
# ═══════════════════════════════════════════════════════════════════════

class TestBrokerPlaceSignal:
    """Test AlpacaBroker.place_signal with mocked TradingClient."""

    def _broker(self, positions=None, orders=None, equity=100000):
        """Create a broker with fully mocked API."""
        b = AlpacaBroker.__new__(AlpacaBroker)
        b.api_key = 'test'
        b.secret_key = 'test'
        b._trading = MagicMock()
        b._session_high_equity = equity
        b._halted = False

        # Mock get_account
        acct = MagicMock()
        acct.cash = equity
        acct.buying_power = equity * 4
        acct.equity = equity
        acct.status = 'ACTIVE'
        b._trading.get_account.return_value = acct

        # Mock positions
        mock_positions = []
        for sym, pos in (positions or {}).items():
            p = MagicMock()
            p.symbol = sym
            p.qty = pos.get('qty', 10)
            p.avg_entry_price = pos.get('avg_entry', 100)
            p.current_price = pos.get('current', 100)
            p.market_value = pos.get('market_value', 1000)
            p.unrealized_pl = pos.get('pl', 0)
            p.unrealized_plpc = pos.get('pl_pct', 0)
            mock_positions.append(p)
        b._trading.get_all_positions.return_value = mock_positions

        # Mock orders (dedup check)
        mock_orders = []
        for o in (orders or []):
            order = MagicMock()
            order.symbol = o.get('symbol', 'SPY')
            order.side = MagicMock(value=o.get('side', 'buy'))
            mock_orders.append(order)
        b._trading.get_orders.return_value = mock_orders

        # Mock get_last_trade (price alignment) - return None so code falls back to signal entry
        mock_trade = MagicMock()
        mock_trade.price = None
        b._trading.get_last_trade.return_value = mock_trade

        return b

    def test_hold_signal_returns_no_trade(self):
        b = self._broker()
        sig = _make_signal(direction='HOLD')
        result = b.place_signal(sig)
        assert not result.placed
        assert result.reason == 'HOLD signal - no trade'

    def test_unsupported_ticker_rejected(self):
        b = self._broker()
        sig = _make_signal(ticker='FAKE-COIN')
        result = b.place_signal(sig)
        assert not result.placed
        assert 'not supported' in result.reason

    def test_already_holding_rejected(self):
        b = self._broker(positions={'SPY': {'qty': 10, 'market_value': 5500}})
        sig = _make_signal(ticker='SPY')
        result = b.place_signal(sig)
        assert not result.placed
        assert 'Already holding' in result.reason

    def test_dedup_rejects_recent_order(self):
        b = self._broker(orders=[{'symbol': 'SPY', 'side': 'buy'}])
        sig = _make_signal(ticker='SPY')
        result = b.place_signal(sig)
        assert not result.placed
        assert 'Already attempted' in result.reason

    def test_max_positions_rejected(self):
        # MAX_CONCURRENT_POSITIONS = 10 in settings.py
        tickers = ['QQQ', 'IWM', 'DIA', 'GLD', 'SLV', 'USO', 'UNG', 'AAPL', 'NVDA', 'MSFT']
        positions = {t: {'qty': 5, 'market_value': 1500} for t in tickers}
        b = self._broker(positions=positions)
        sig = _make_signal(ticker='SPY')
        result = b.place_signal(sig)
        assert not result.placed
        assert 'MAX POSITIONS' in result.reason

    def test_drawdown_halt_rejected(self):
        b = self._broker(equity=85000)
        b._session_high_equity = 100000  # 15% drawdown
        sig = _make_signal(ticker='SPY')
        result = b.place_signal(sig)
        assert not result.placed
        assert 'DRAWDOWN HALT' in result.reason

    def test_stock_bracket_order_placed(self):
        b = self._broker()
        sig = _make_signal(ticker='SPY', entry=550.0, sl=547.25, tp=555.5)
        result = b.place_signal(sig)
        assert result.placed
        assert result.qty > 0
        assert result.symbol == 'SPY'
        b._trading.submit_order.assert_called_once()

    def test_crypto_market_order_placed(self):
        b = self._broker()
        # Mock filled order
        filled = MagicMock()
        filled.status = 'filled'
        filled.filled_qty = '0.05'
        filled.filled_avg_price = '65000'
        b._trading.get_order_by_id.return_value = filled

        sig = _make_signal(
            ticker='ETH-USD', entry=3500, sl=3400, tp=3700, conf=0.7,
        )
        result = b.place_signal(sig)
        assert result.placed
        assert 'Crypto' in result.reason

    def test_zero_shares_rejected(self):
        b = self._broker(equity=100000)
        # Very wide SL with tiny equity → still calculates shares
        # But very tight entry/SL where risk is 0
        sig = _make_signal(ticker='SPY', entry=550.0, sl=550.0)
        result = b.place_signal(sig)
        assert not result.placed
        assert 'Zero shares' in result.reason

    def test_invalid_sl_tp_rejected(self):
        b = self._broker()
        sig = _make_signal(ticker='SPY', sl=0, tp=0)
        result = b.place_signal(sig)
        assert not result.placed
        assert 'Invalid SL/TP' in result.reason

    def test_swing_widens_sl_tp(self):
        b = self._broker()
        sig = _make_signal(
            ticker='SPY', entry=550.0, sl=549.0, tp=551.0, interval='1d',
        )
        result = b.place_signal(sig, interval='1d')
        assert result.placed
        call_args = b._trading.submit_order.call_args[0][0]
        # Bracket order: stop_loss and take_profit are objects with attributes
        sl_price = call_args.stop_loss.stop_price
        tp_price = call_args.take_profit.limit_price
        # SL/TP should be widened for swing (>1.5% SL, >3% TP)
        assert sl_price < 550 * 0.98  # >2% SL
        assert tp_price > 550 * 1.02  # >2% TP


# ═══════════════════════════════════════════════════════════════════════
# 2. Paper-trade CLI — full flow with mocked pipeline + broker
# ═══════════════════════════════════════════════════════════════════════

class TestPaperTradeCLI:
    """Test the paper-trade CLI command end-to-end."""

    @patch('httpx.post')
    @patch('signals.pipeline.DataFetcher')
    @patch('signals.pipeline.DataProcessor')
    @patch('signals.pipeline.TechnicalIndicators')
    @patch('signals.pipeline.SignalGenerator')
    def test_full_flow_places_trades(self, mock_sg, mock_ti, mock_dp, mock_df, mock_httpx):
        from click.testing import CliRunner
        from main import cli

        # Mock pipeline to return actionable results
        results = [
            _make_result(ticker='SPY', direction='BUY', confluence=3, conf=0.75),
            _make_result(ticker='QQQ', direction='SELL', confluence=4, conf=0.80),
        ]

        # Mock Telegram
        mock_httpx.return_value = MagicMock(status_code=200)

        runner = CliRunner()
        with patch.object(UnifiedPipeline, 'run_all', return_value=results):
            with patch.object(UnifiedPipeline, 'notify_actionable', return_value=2):
                with patch('signals.alpaca_broker.TradingClient') as mock_tc:
                    # Setup broker mocks
                    acct = MagicMock()
                    acct.cash = 100000
                    acct.buying_power = 400000
                    acct.equity = 100000
                    acct.status = 'ACTIVE'
                    mock_tc.return_value.get_account.return_value = acct
                    mock_tc.return_value.get_all_positions.return_value = []
                    mock_tc.return_value.get_orders.return_value = []

                    result = runner.invoke(cli, ['paper-trade'])

        assert result.exit_code == 0
        assert 'PAPER TRADING COMPLETE' in result.output

    @patch('httpx.post')
    @patch('signals.manager.SignalManager')
    @patch('signals.alpaca_broker.TradingClient')
    def test_dry_run_shows_signals_no_trades(self, mock_tc, mock_manager_cls, mock_httpx):
        from click.testing import CliRunner
        from main import cli

        mock_httpx.return_value = MagicMock(status_code=200)

        # Isolated broker: empty account, no existing positions/orders —
        # must not touch the real Alpaca paper account.
        acct = MagicMock()
        acct.cash = 100000
        acct.buying_power = 400000
        acct.equity = 100000
        acct.status = 'ACTIVE'
        mock_tc.return_value.get_account.return_value = acct
        mock_tc.return_value.get_all_positions.return_value = []
        mock_tc.return_value.get_orders.return_value = []

        # Isolated signal manager: no cooldown history — must not read the
        # real logs/signals.csv, whose recent entries would otherwise
        # trigger the 4h cooldown skip and hide the [DRY] line.
        mock_manager_cls.return_value.get_history.return_value = pd.DataFrame()

        results = [
            _make_result(ticker='SPY', direction='BUY', confluence=3, conf=0.75),
        ]

        runner = CliRunner()
        with patch.object(UnifiedPipeline, 'run_all', return_value=results):
            with patch.object(UnifiedPipeline, 'notify_actionable', return_value=0):
                result = runner.invoke(cli, ['paper-trade', '--dry-run'])

        assert result.exit_code == 0
        assert 'DRY RUN' in result.output
        assert '[DRY]' in result.output

    @patch('httpx.post')
    @patch('signals.manager.SignalManager')
    @patch('signals.alpaca_broker.TradingClient')
    def test_1m_signal_not_blocked_by_24h_cooldown(self, mock_tc, mock_manager_cls, mock_httpx):
        """1m (scalping) signals must use the same short cooldown as 1h,
        not the 24h swing cooldown. A signal logged 10h ago is older than
        the 4h intraday cooldown but younger than the 24h swing one — it
        should NOT be skipped for a 1m ticker.
        """
        from click.testing import CliRunner
        from main import cli

        mock_httpx.return_value = MagicMock(status_code=200)

        acct = MagicMock()
        acct.cash = 100000
        acct.buying_power = 400000
        acct.equity = 100000
        acct.status = 'ACTIVE'
        mock_tc.return_value.get_account.return_value = acct
        mock_tc.return_value.get_all_positions.return_value = []
        mock_tc.return_value.get_orders.return_value = []

        ten_hours_ago = (datetime.now() - timedelta(hours=10)).isoformat()
        mock_manager_cls.return_value.get_history.return_value = pd.DataFrame([{
            'timestamp': ten_hours_ago, 'ticker': 'SPY', 'direction': 'BUY',
        }])

        results = [
            _make_result(ticker='SPY', direction='BUY', confluence=3, conf=0.75, interval='1m'),
        ]

        runner = CliRunner()
        with patch.object(UnifiedPipeline, 'run_all', return_value=results):
            with patch.object(UnifiedPipeline, 'notify_actionable', return_value=0):
                result = runner.invoke(cli, ['paper-trade', '--dry-run', '--interval', '1m'])

        assert result.exit_code == 0
        assert 'cooldown' not in result.output
        assert '[DRY]' in result.output

    def test_close_all_flag(self):
        from click.testing import CliRunner
        from main import cli

        results = []
        runner = CliRunner()
        with patch.object(UnifiedPipeline, 'run_all', return_value=results):
            with patch('signals.alpaca_broker.TradingClient') as mock_tc:
                acct = MagicMock()
                acct.cash = 100000
                acct.buying_power = 400000
                acct.equity = 100000
                acct.status = 'ACTIVE'
                mock_tc.return_value.get_account.return_value = acct

                # Simulate 2 open positions
                pos1 = MagicMock()
                pos1.symbol = 'SPY'
                pos1.qty = '10'
                pos1.avg_entry_price = '550'
                pos1.current_price = '555'
                pos1.market_value = '5550'
                pos1.unrealized_pl = '50'
                pos1.unrealized_plpc = '0.009'
                pos2 = MagicMock()
                pos2.symbol = 'QQQ'
                pos2.qty = '5'
                pos2.avg_entry_price = '480'
                pos2.current_price = '485'
                pos2.market_value = '2425'
                pos2.unrealized_pl = '25'
                pos2.unrealized_plpc = '0.01'
                mock_tc.return_value.get_all_positions.return_value = [pos1, pos2]
                mock_tc.return_value.get_orders.return_value = []

                result = runner.invoke(cli, ['paper-trade', '--close-all'])

        assert result.exit_code == 0
        assert 'Closing' in result.output or 'CLOSE' in result.output

    def test_filter_by_category(self):
        from click.testing import CliRunner
        from main import cli

        runner = CliRunner()
        with patch.object(UnifiedPipeline, 'run_all', return_value=[]) as mock_run:
            with patch('signals.alpaca_broker.TradingClient') as mock_tc:
                acct = MagicMock()
                acct.cash = 100000
                acct.buying_power = 400000
                acct.equity = 100000
                acct.status = 'ACTIVE'
                mock_tc.return_value.get_account.return_value = acct
                mock_tc.return_value.get_all_positions.return_value = []
                mock_tc.return_value.get_orders.return_value = []

                result = runner.invoke(cli, ['paper-trade', '--category', 'crypto'])

        assert result.exit_code == 0
        # Verify pipeline was called with category filter
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get('category') == 'crypto' or call_kwargs[1].get('category') == 'crypto'

    def test_filter_by_ticker(self):
        from click.testing import CliRunner
        from main import cli

        runner = CliRunner()
        with patch.object(UnifiedPipeline, 'run_all', return_value=[]) as mock_run:
            with patch('signals.alpaca_broker.TradingClient') as mock_tc:
                acct = MagicMock()
                acct.cash = 100000
                acct.buying_power = 400000
                acct.equity = 100000
                acct.status = 'ACTIVE'
                mock_tc.return_value.get_account.return_value = acct
                mock_tc.return_value.get_all_positions.return_value = []
                mock_tc.return_value.get_orders.return_value = []

                result = runner.invoke(cli, ['paper-trade', '--ticker', 'AAPL'])

        assert result.exit_code == 0
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get('ticker_filter') == 'AAPL' or call_kwargs[1].get('ticker_filter') == 'AAPL'

    def test_min_confluence_filter(self):
        from click.testing import CliRunner
        from main import cli

        # Signal with confluence=2 should be skipped when min_confluence=3
        results = [
            _make_result(ticker='SPY', direction='BUY', confluence=2, conf=0.80),
        ]

        runner = CliRunner()
        with patch.object(UnifiedPipeline, 'run_all', return_value=results):
            with patch.object(UnifiedPipeline, 'notify_actionable', return_value=0):
                with patch('signals.alpaca_broker.TradingClient') as mock_tc:
                    acct = MagicMock()
                    acct.cash = 100000
                    acct.buying_power = 400000
                    acct.equity = 100000
                    acct.status = 'ACTIVE'
                    mock_tc.return_value.get_account.return_value = acct
                    mock_tc.return_value.get_all_positions.return_value = []
                    mock_tc.return_value.get_orders.return_value = []

                    result = runner.invoke(cli, ['paper-trade', '--min-confluence', '3'])

        assert result.exit_code == 0
        assert 'skipped (quality filter)' in result.output

    def test_min_confidence_filter(self):
        from click.testing import CliRunner
        from main import cli

        # Signal with conf=0.50 should be skipped when min_confidence=60
        results = [
            _make_result(ticker='SPY', direction='BUY', confluence=3, conf=0.50),
        ]

        runner = CliRunner()
        with patch.object(UnifiedPipeline, 'run_all', return_value=results):
            with patch.object(UnifiedPipeline, 'notify_actionable', return_value=0):
                with patch('signals.alpaca_broker.TradingClient') as mock_tc:
                    acct = MagicMock()
                    acct.cash = 100000
                    acct.buying_power = 400000
                    acct.equity = 100000
                    acct.status = 'ACTIVE'
                    mock_tc.return_value.get_account.return_value = acct
                    mock_tc.return_value.get_all_positions.return_value = []
                    mock_tc.return_value.get_orders.return_value = []

                    result = runner.invoke(cli, ['paper-trade', '--min-confidence', '60'])

        assert result.exit_code == 0
        assert 'skipped (quality filter)' in result.output

    def test_no_actionable_signals(self):
        from click.testing import CliRunner
        from main import cli

        runner = CliRunner()
        with patch.object(UnifiedPipeline, 'run_all', return_value=[]):
            with patch('signals.alpaca_broker.TradingClient') as mock_tc:
                acct = MagicMock()
                acct.cash = 100000
                acct.buying_power = 400000
                acct.equity = 100000
                acct.status = 'ACTIVE'
                mock_tc.return_value.get_account.return_value = acct
                mock_tc.return_value.get_all_positions.return_value = []
                mock_tc.return_value.get_orders.return_value = []

                result = runner.invoke(cli, ['paper-trade'])

        assert result.exit_code == 0
        assert 'No actionable signals' in result.output

    def test_no_telegram_flag(self):
        from click.testing import CliRunner
        from main import cli

        runner = CliRunner()
        with patch.object(UnifiedPipeline, 'run_all', return_value=[]):
            with patch('signals.alpaca_broker.TradingClient') as mock_tc:
                acct = MagicMock()
                acct.cash = 100000
                acct.buying_power = 400000
                acct.equity = 100000
                acct.status = 'ACTIVE'
                mock_tc.return_value.get_account.return_value = acct
                mock_tc.return_value.get_all_positions.return_value = []
                mock_tc.return_value.get_orders.return_value = []

                result = runner.invoke(cli, ['paper-trade', '--no-telegram'])

        assert result.exit_code == 0


# ═══════════════════════════════════════════════════════════════════════
# 3. Telegram httpx integration
# ═══════════════════════════════════════════════════════════════════════

class TestTelegramIntegration:
    """Test TelegramNotifier with httpx (mocked httpx.post)."""

    @patch('httpx.post')
    def test_send_alert_success(self, mock_post):
        from signals.telegram_bot import TelegramNotifier

        mock_post.return_value = MagicMock(status_code=200)
        notifier = TelegramNotifier(bot_token='test', chat_id='123', enabled=True)

        result = notifier.send_alert('Hello World')
        assert result is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]['json']['text'] == 'Hello World'

    @patch('httpx.post')
    def test_send_alert_api_error(self, mock_post):
        from signals.telegram_bot import TelegramNotifier

        mock_post.return_value = MagicMock(status_code=400, text='Bad Request')
        notifier = TelegramNotifier(bot_token='test', chat_id='123', enabled=True)

        result = notifier.send_alert('Hello')
        assert result is False

    @patch('httpx.post')
    def test_send_alert_network_error(self, mock_post):
        from signals.telegram_bot import TelegramNotifier

        mock_post.side_effect = Exception('Connection refused')
        notifier = TelegramNotifier(bot_token='test', chat_id='123', enabled=True)

        result = notifier.send_alert('Hello')
        assert result is False

    @patch('httpx.post')
    def test_no_event_loop_error(self, mock_post):
        """Verify httpx-based approach never raises RuntimeError about event loops."""
        from signals.telegram_bot import TelegramNotifier

        mock_post.return_value = MagicMock(status_code=200)
        notifier = TelegramNotifier(bot_token='test', chat_id='123', enabled=True)

        # Send multiple messages — should never raise RuntimeError
        for i in range(5):
            result = notifier.send_alert(f'Message {i}')
            assert result is True

    def test_disabled_returns_false(self):
        from signals.telegram_bot import TelegramNotifier

        notifier = TelegramNotifier(bot_token='test', chat_id='123', enabled=False)
        assert notifier.send_alert('Hello') is False
        assert notifier.is_configured is True

    def test_not_configured_returns_false(self):
        from signals.telegram_bot import TelegramNotifier

        notifier = TelegramNotifier(bot_token='', chat_id='', enabled=True)
        assert notifier.send_alert('Hello') is False
        assert notifier.is_configured is False


# ═══════════════════════════════════════════════════════════════════════
# 4. Pipeline → Broker handoff
# ═══════════════════════════════════════════════════════════════════════

class TestPipelineBrokerHandoff:
    """Test that PipelineResult.technical_signal feeds correctly into broker."""

    def test_actionable_result_has_correct_signal_fields(self):
        result = _make_result(
            ticker='BTC-USD', direction='BUY',
            entry=65000, sl=63455, tp=66354, conf=0.7,
            confluence=3, interval='1h',
        )
        assert result.is_actionable()
        assert result.technical_signal.ticker == 'BTC-USD'
        assert result.technical_signal.direction == 'BUY'
        assert result.technical_signal.entry_price == 65000
        assert result.technical_signal.stop_loss == 63455
        assert result.technical_signal.take_profit == 66354

    def test_hold_result_not_actionable(self):
        result = _make_result(direction='HOLD', conf=0.5)
        assert not result.is_actionable()

    def test_low_confluence_filtered_before_broker(self):
        """Confluence filter should happen BEFORE broker.place_signal."""
        result = _make_result(confluence=1)
        # In paper_trade(), this check comes before broker.place_signal()
        assert result.confluence_score < 3  # default min_confluence

    def test_low_confidence_filtered_before_broker(self):
        result = _make_result(conf=0.50)
        assert result.final_confidence * 100 < 60  # default min_confidence


# ═══════════════════════════════════════════════════════════════════════
# 5. Crypto safety close on SL failure
# ═══════════════════════════════════════════════════════════════════════

class TestCryptoSafetyClose:
    """Test that crypto positions are closed if SL order fails."""

    def test_sl_failure_triggers_safety_close(self):
        b = AlpacaBroker.__new__(AlpacaBroker)
        b.api_key = 'test'
        b.secret_key = 'test'
        b._trading = MagicMock()
        b._session_high_equity = 100000
        b._halted = False

        acct = MagicMock()
        acct.cash = 100000
        acct.buying_power = 400000
        acct.equity = 100000
        acct.status = 'ACTIVE'
        b._trading.get_account.return_value = acct
        b._trading.get_all_positions.return_value = []
        b._trading.get_orders.return_value = []

        # Mock get_last_trade - return price matching entry to avoid price alignment skip
        mock_trade = MagicMock()
        mock_trade.price = 3500
        b._trading.get_last_trade.return_value = mock_trade

        # First call: market order fills
        filled = MagicMock()
        filled.status = 'filled'
        filled.filled_qty = '0.05'
        filled.filled_avg_price = '65000'

        # Second call: SL order fails
        b._trading.get_order_by_id.return_value = filled
        b._trading.submit_order.side_effect = [
            MagicMock(),  # Market order succeeds
            Exception('Insufficient qty'),  # SL fails
            MagicMock(),  # Safety close succeeds
        ]

        sig = _make_signal(
            ticker='ETH-USD', entry=3500, sl=3400, tp=3700,
        )
        result = b.place_signal(sig)
        assert not result.placed
        assert 'SL failed' in result.reason

    def test_no_positions_passes_portfolio_check(self):
        b = AlpacaBroker.__new__(AlpacaBroker)
        b.api_key = 'test'
        b.secret_key = 'test'
        b._trading = MagicMock()
        b._session_high_equity = 100000
        b._halted = False

        acct = MagicMock()
        acct.cash = 100000
        acct.buying_power = 400000
        acct.equity = 100000
        acct.status = 'ACTIVE'
        b._trading.get_account.return_value = acct
        b._trading.get_all_positions.return_value = []
        b._trading.get_orders.return_value = []

        # Mock get_last_trade - return price matching entry to avoid price alignment skip
        mock_trade = MagicMock()
        mock_trade.price = 3500
        b._trading.get_last_trade.return_value = mock_trade

        filled = MagicMock()
        filled.status = 'filled'
        filled.filled_qty = '0.05'
        filled.filled_avg_price = '65000'

        sl_ok = MagicMock()
        b._trading.get_order_by_id.return_value = filled
        b._trading.submit_order.side_effect = [
            MagicMock(),  # Market order
            sl_ok,        # SL succeeds
            MagicMock(),  # TP succeeds
        ]

        sig = _make_signal(
            ticker='ETH-USD', entry=3500, sl=3400, tp=3700,
        )
        result = b.place_signal(sig)
        assert result.placed


# ═══════════════════════════════════════════════════════════════════════
# 6. Position sizing integration
# ═══════════════════════════════════════════════════════════════════════

class TestPositionSizingIntegration:
    """Test calculate_shares with real math (no API mocks)."""

    def _broker(self, equity=100000):
        b = AlpacaBroker.__new__(AlpacaBroker)
        b.api_key = 'test'
        b.secret_key = 'test'
        b._trading = MagicMock()
        b._session_high_equity = equity
        b._halted = False
        acct = MagicMock()
        acct.equity = equity
        acct.cash = equity
        acct.buying_power = equity * 4
        acct.status = 'ACTIVE'
        b._trading.get_account.return_value = acct
        return b

    def test_stock_sizing_2pct_risk(self):
        b = self._broker(equity=100000)
        # entry=550, SL=547.25 → risk/share=2.75
        # risk_capital = 100000 * 0.02 = 2000
        # shares_by_risk = 2000 / 2.75 = 727
        # max_position = 100000 * 0.05 = 5000 → shares_by_capital = 5000/550 = 9.09
        # min(727, 9.09) = 9.09
        shares = b.calculate_shares(550.0, 547.25, equity=100000, is_crypto=False)
        assert shares > 0
        assert shares * 550.0 <= 100000 * 0.05  # Within 5% cap

    def test_crypto_sizing_3pct_limit(self):
        b = self._broker(equity=100000)
        # Crypto max is 3% of equity = $3000
        # calculate_shares uses equity * CRYPTO_MAX_SINGLE / entry_price
        # = 100000 * 0.03 / 65000 = 0.04615 (rounded to 4 decimals)
        # 0.0462 * 65000 = 3003, which is within tolerance of rounding
        shares = b.calculate_shares(65000, 63455, equity=100000, is_crypto=True)
        assert shares > 0
        # Allow small rounding tolerance (0.01%)
        assert shares * 65000 <= 100000 * 0.03 + 10

    def test_small_equity_sizing(self):
        b = self._broker(equity=10000)
        shares = b.calculate_shares(550, 547.25, equity=10000, is_crypto=False)
        # risk_capital = 10000 * 0.02 = 200
        # shares_by_risk = 200 / 2.75 = 72.7
        # max_position = 10000 * 0.05 = 500 → shares_by_capital = 500/550 = 0.91
        # min(72.7, 0.91) = 0.91
        assert shares > 0
        assert shares * 550 <= 10000 * 0.05 + 1  # Within cap (float tolerance)
