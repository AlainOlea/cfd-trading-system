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
        max_position_pct: float = 0.20,
    ) -> int:
        """Calculate shares respecting both risk and account size limits."""
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share <= 0:
            return 0
        shares_by_risk = risk_capital / risk_per_share

        acct = self.get_account_summary()
        equity = acct.get('equity', 100000)
        max_position_value = equity * max_position_pct
        shares_by_capital = max_position_value / entry_price

        shares = min(shares_by_risk, shares_by_capital)
        return max(1, round(shares))

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
            if direction == 'BUY':
                side = OrderSide.BUY
                sl_side = OrderSide.SELL
                if sl >= entry or tp <= entry:
                    return TradeResult(symbol, direction, shares, entry, sl, tp, conf,
                                       False, f"SL/TP on wrong side of entry (BUY: SL<{entry}<TP)")
            else:
                side = OrderSide.SELL
                sl_side = OrderSide.BUY
                if sl <= entry or tp >= entry:
                    return TradeResult(symbol, direction, shares, entry, sl, tp, conf,
                                       False, f"SL/TP on wrong side of entry (SELL: TP<{entry}<SL)")

            order = MarketOrderRequest(
                symbol=alpaca_symbol,
                qty=shares,
                side=side,
                time_in_force=TimeInForce.DAY,
                order_class=OrderClass.BRACKET,
                take_profit={'limit_price': round(tp, 2)},
                stop_loss={'stop_price': round(sl, 2)},
            )

            self.trading.submit_order(order)
            logger.info(f"BRACKET {direction} {shares} {alpaca_symbol} @ ~{entry:.2f} | SL={sl:.2f} TP={tp:.2f} | conf={conf:.0%}")

            return TradeResult(symbol, direction, shares, entry, sl, tp, conf,
                               True, f"Bracket order placed: {direction} {shares} shares")

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
