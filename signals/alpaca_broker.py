"""
Alpaca Paper Trading Broker
============================
Connects to Alpaca Markets paper trading sandbox to execute signals
with bracket orders (entry + stop-loss + take-profit in one call).

Zero real money. $100k virtual capital. Perfect for testing signals.
"""

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

logger = logging.getLogger(__name__)

ALPACA_STOCKS = {'SPY', 'QQQ', 'IWM', 'GLD', 'AAPL', 'NVDA', 'MSFT'}
ALPACA_CRYPTO = {'BTC-USD': 'BTC/USD', 'ETH-USD': 'ETH/USD', 'SOL-USD': 'SOL/USD'}
DEFAULT_RISK_CAPITAL = 2000.0  # 2% of $100k
MAX_POSITION_PCT = 0.05       # 5% max per position (~$5k)
MIN_POSITION_VALUE = 100.0    # Don't bother with trades smaller than $100


def _to_alpaca_symbol(ticker: str) -> str:
    """Convert our ticker format to Alpaca's format."""
    if ticker in ALPACA_CRYPTO:
        return ALPACA_CRYPTO[ticker]
    return ticker


def _is_stock(ticker: str) -> bool:
    return ticker in ALPACA_STOCKS


def _is_crypto(ticker: str) -> bool:
    return ticker in ALPACA_CRYPTO


@dataclass
class TradeResult:
    symbol: str
    side: str
    qty: int
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float
    placed: bool
    reason: str


class AlpacaBroker:
    """Paper trading broker for Alpaca Markets."""

    def __init__(self):
        self.api_key = os.getenv('ALPACA_API_KEY', '')
        self.secret_key = os.getenv('ALPACA_SECRET_KEY', '')
        self._trading: TradingClient | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.secret_key)

    @property
    def trading(self) -> TradingClient:
        if self._trading is None:
            if not self.is_configured:
                raise RuntimeError("Alpaca API keys not configured")
            self._trading = TradingClient(self.api_key, self.secret_key, paper=True)
        return self._trading

    def get_account_summary(self) -> dict:
        try:
            acct = self.trading.get_account()
            return {
                'cash': float(acct.cash),
                'buying_power': float(acct.buying_power),
                'equity': float(acct.equity),
                'status': str(acct.status),
            }
        except Exception as e:
            logger.error(f"Failed to get account: {e}")
            return {}

    def get_open_positions(self) -> dict[str, dict]:
        positions = {}
        try:
            for p in self.trading.get_all_positions():
                positions[p.symbol] = {
                    'qty': float(p.qty),
                    'avg_entry': float(p.avg_entry_price),
                    'current_price': float(p.current_price),
                    'unrealized_pl': float(p.unrealized_pl),
                    'unrealized_pl_pct': float(p.unrealized_plpc),
                }
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
        return positions

    def has_position(self, symbol: str) -> bool:
        return symbol in self.get_open_positions()

    def calculate_shares(
        self,
        entry_price: float,
        stop_loss: float,
        risk_capital: float = DEFAULT_RISK_CAPITAL,
        max_position_pct: float = MAX_POSITION_PCT,
    ) -> float:
        """Calculate position size respecting risk and account limits.

        Returns fractional shares for small positions, whole for larger ones.
        Uses notional value cap to prevent single positions dominating account.
        """
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share <= 0:
            return 0.0
        shares_by_risk = risk_capital / risk_per_share

        acct = self.get_account_summary()
        cash = acct.get('cash', acct.get('equity', 100000))
        max_position_value = cash * max_position_pct
        shares_by_capital = max_position_value / entry_price

        shares = min(shares_by_risk, shares_by_capital)

        # Round to 4 decimals for fractional shares
        shares = round(shares, 4)

        # Don't trade if position value would be less than $100
        if shares * entry_price < MIN_POSITION_VALUE:
            return 0.0

        return shares

    def place_signal(self, signal) -> TradeResult:
        """Execute a trading signal as a bracket order on Alpaca paper.

        Args:
            signal: Signal dataclass with direction, ticker, entry_price,
                    stop_loss, take_profit, confidence.

        Returns:
            TradeResult with execution status.
        """
        symbol = signal.ticker
        direction = signal.direction
        entry = signal.entry_price
        sl = signal.stop_loss
        tp = signal.take_profit
        conf = signal.confidence

        if direction == 'HOLD':
            return TradeResult(symbol, 'HOLD', 0, entry, sl, tp, conf,
                               False, "HOLD signal - no trade")

        alpaca_symbol = _to_alpaca_symbol(symbol)
        if not _is_stock(symbol) and not _is_crypto(symbol):
            return TradeResult(symbol, direction, 0, entry, sl, tp, conf,
                               False, f"{symbol} not supported by Alpaca")

        if self.has_position(alpaca_symbol):
            return TradeResult(symbol, direction, 0, entry, sl, tp, conf,
                               False, f"Already holding {symbol}")

        if sl <= 0 or tp <= 0:
            return TradeResult(symbol, direction, 0, entry, sl, tp, conf,
                               False, "Invalid SL/TP values")

        shares = self.calculate_shares(entry, sl)
        if shares <= 0:
            return TradeResult(symbol, direction, 0, entry, sl, tp, conf,
                               False, "Zero shares calculated")

        try:
            is_crypto = _is_crypto(symbol)

            if direction == 'BUY':
                side = OrderSide.BUY
                if sl >= entry or tp <= entry:
                    return TradeResult(symbol, direction, shares, entry, sl, tp, conf,
                                       False, f"SL/TP on wrong side of entry (BUY: SL<{entry}<TP)")
            else:
                side = OrderSide.SELL
                if sl <= entry or tp >= entry:
                    return TradeResult(symbol, direction, shares, entry, sl, tp, conf,
                                       False, f"SL/TP on wrong side of entry (SELL: TP<{entry}<SL)")

            if is_crypto:
                # Crypto: use notional value (buy $X worth) with simple market order
                notional = round(shares * entry, 2)
                order = MarketOrderRequest(
                    symbol=alpaca_symbol,
                    notional=notional,
                    side=side,
                    time_in_force=TimeInForce.GTC,
                )
                self.trading.submit_order(order)
                logger.info(f"CRYPTO {direction} {alpaca_symbol}: ${notional:.0f} notional @ ~{entry:.2f}")
                return TradeResult(symbol, direction, 0, entry, sl, tp, conf,
                                   True, f"Crypto: ${notional:,.0f} {direction} (SL=${sl:.2f} TP=${tp:.2f})")
            else:
                # Stocks/ETFs: whole shares with bracket order for auto SL/TP
                qty = max(1, round(shares))
                order = MarketOrderRequest(
                    symbol=alpaca_symbol,
                    qty=qty,
                    side=side,
                    time_in_force=TimeInForce.DAY,
                    order_class=OrderClass.BRACKET,
                    take_profit={'limit_price': round(tp, 2)},
                    stop_loss={'stop_price': round(sl, 2)},
                )
                self.trading.submit_order(order)
                logger.info(f"BRACKET {direction} {qty} {alpaca_symbol} @ ~{entry:.2f} | SL={sl:.2f} TP={tp:.2f}")
                return TradeResult(symbol, direction, qty, entry, sl, tp, conf,
                                   True, f"Bracket: {direction} {qty} sh")

        except Exception as e:
            logger.error(f"Order failed for {symbol}: {e}")
            return TradeResult(symbol, direction, shares, entry, sl, tp, conf,
                               False, str(e))

    def close_position(self, symbol: str) -> TradeResult:
        try:
            pos = self.trading.get_open_position(symbol)
            qty = float(pos.qty)
            side = OrderSide.SELL if float(pos.qty) > 0 else OrderSide.BUY
            qty = abs(qty)

            order = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side,
                time_in_force=TimeInForce.GTC,
            )
            self.trading.submit_order(order)
            logger.info(f"CLOSE {symbol}: {side.value} {qty} shares")
            return TradeResult(symbol, 'CLOSE', qty, 0, 0, 0, 0, True, f"Closed {symbol}")
        except Exception as e:
            logger.error(f"Close failed for {symbol}: {e}")
            return TradeResult(symbol, 'CLOSE', 0, 0, 0, 0, 0, False, str(e))

    def close_all(self) -> list[TradeResult]:
        results = []
        for symbol in self.get_open_positions():
            results.append(self.close_position(symbol))
        return results

    def get_trade_history(self, days: int = 30) -> list[dict]:
        """Get filled orders with calculated P&L.

        Groups bracket orders to compute entry-to-exit profit per trade.
        """
        from datetime import datetime, timedelta
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus

        after = datetime.now() - timedelta(days=days)
        filled_req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=500, after=after)
        all_orders = self.trading.get_orders(filter=filled_req)

        trades = []
        for o in all_orders:
            if o.order_class == OrderClass.BRACKET and o.legs:
                trade = self._parse_bracket_trade(o)
                if trade:
                    trades.append(trade)
            elif o.filled_avg_price and float(o.filled_qty or 0) > 0:
                trades.append({
                    'symbol': o.symbol,
                    'side': str(o.side),
                    'qty': float(o.qty),
                    'entry': float(o.filled_avg_price),
                    'exit': 0.0,
                    'pnl': 0.0,
                    'pnl_pct': 0.0,
                    'filled_at': str(o.filled_at),
                    'type': 'manual',
                })

        return sorted(trades, key=lambda t: t.get('filled_at', ''))

    def _parse_bracket_trade(self, parent_order) -> dict | None:
        """Extract entry and exit from a bracket order."""
        try:
            entry_leg = parent_order
            entry_price = float(entry_leg.filled_avg_price or 0)
            entry_qty = float(entry_leg.filled_qty or 0)
            if entry_price <= 0 or entry_qty <= 0:
                return None

            exit_price = 0.0
            exit_side = None
            for leg in parent_order.legs:
                if leg.filled_avg_price and float(leg.filled_qty or 0) > 0:
                    exit_price = float(leg.filled_avg_price)
                    exit_side = str(leg.side)
                    break

            if exit_price <= 0:
                return None

            if entry_leg.side == OrderSide.BUY:
                pnl = (exit_price - entry_price) * entry_qty
                pnl_pct = ((exit_price - entry_price) / entry_price) * 100
            else:
                pnl = (entry_price - exit_price) * entry_qty
                pnl_pct = ((entry_price - exit_price) / entry_price) * 100

            return {
                'symbol': entry_leg.symbol,
                'side': str(entry_leg.side),
                'qty': entry_qty,
                'entry': entry_price,
                'exit': exit_price,
                'pnl': round(pnl, 2),
                'pnl_pct': round(pnl_pct, 2),
                'filled_at': str(entry_leg.filled_at),
                'type': 'bracket',
                'exit_type': 'TP' if exit_side != str(entry_leg.side) else 'manual',
            }
        except Exception as e:
            logger.debug(f"Could not parse bracket trade: {e}")
            return None

    def get_performance(self, days: int = 30) -> dict:
        """Calculate performance metrics from trade history."""
        trades = self.get_trade_history(days)
        if not trades:
            return {'trades': 0, 'win_rate': 0, 'total_pnl': 0,
                    'avg_win': 0, 'avg_loss': 0, 'profit_factor': 0,
                    'best': 0, 'worst': 0}

        wins = [t for t in trades if t['pnl'] > 0]
        losses = [t for t in trades if t['pnl'] < 0]
        total_pnl = sum(t['pnl'] for t in trades)
        gross_profit = sum(t['pnl'] for t in wins)
        gross_loss = abs(sum(t['pnl'] for t in losses))

        return {
            'trades': len(trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': round(len(wins) / len(trades) * 100, 1) if trades else 0,
            'total_pnl': round(total_pnl, 2),
            'avg_win': round(sum(t['pnl'] for t in wins) / len(wins), 2) if wins else 0,
            'avg_loss': round(sum(t['pnl'] for t in losses) / len(losses), 2) if losses else 0,
            'profit_factor': round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0,
            'best': round(max(t['pnl'] for t in trades), 2),
            'worst': round(min(t['pnl'] for t in trades), 2),
        }
