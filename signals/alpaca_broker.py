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
from alpaca.trading.requests import MarketOrderRequest, StopOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

logger = logging.getLogger(__name__)

ALPACA_STOCKS = {'SPY', 'QQQ', 'IWM', 'DIA', 'GLD', 'SLV', 'USO', 'UNG', 'AAPL', 'NVDA', 'MSFT', 'AMZN', 'GOOGL', 'META', 'TSLA'}
ALPACA_CRYPTO = {'BTC-USD': 'BTC/USD', 'ETH-USD': 'ETH/USD', 'SOL-USD': 'SOL/USD', 'DOGE-USD': 'DOGE/USD', 'XRP-USD': 'XRP/USD'}
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

    def place_signal(self, signal, interval: str = '1h') -> TradeResult:
        """Execute a trading signal as a bracket order on Alpaca paper.

        Args:
            signal: Signal dataclass with direction, ticker, entry_price,
                    stop_loss, take_profit, confidence.
            interval: '1d' for swing (GTC, 2x SL/TP), '1h' for intraday (DAY).
                      Default '1h' for backward compatibility.

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

        # Widen SL/TP for swing trades (1d signals inherit 1h-tight levels from strategies)
        if interval == '1d':
            sl, tp = self._widen_sl_tp_for_swing(entry, sl, tp, direction)

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
                if direction == 'SELL':
                    return TradeResult(symbol, direction, 0, entry, sl, tp, conf,
                                       False, "Alpaca does not support shorting crypto")
                # Crypto BUY: notional value with simple market order
                notional = round(shares * entry, 2)
                order = MarketOrderRequest(
                    symbol=alpaca_symbol,
                    notional=notional,
                    side=side,
                    time_in_force=TimeInForce.GTC,
                )
                submitted = self.trading.submit_order(order)
                logger.info(f"CRYPTO {direction} {alpaca_symbol}: ${notional:.0f} notional @ ~{entry:.2f}")

                # Place separate SL/TP orders after fill (Alpaca limitation: no bracket for notional)
                import time as _time
                filled_order = submitted
                for _ in range(15):
                    _time.sleep(1)
                    filled_order = self.trading.get_order(submitted.id)
                    if filled_order.status in ('filled', 'expired', 'canceled'):
                        break

                if filled_order.status == 'filled' and filled_order.filled_qty:
                    filled_qty = float(filled_order.filled_qty)
                    filled_price = float(filled_order.filled_avg_price or entry)

                    # Place stop-loss order
                    try:
                        sl_req = StopOrderRequest(
                            symbol=alpaca_symbol,
                            qty=filled_qty,
                            side=OrderSide.SELL,
                            stop_price=round(sl, 2),
                            time_in_force=TimeInForce.GTC,
                        )
                        self.trading.submit_order(sl_req)
                        logger.info(f"CRYPTO SL: {filled_qty} {alpaca_symbol} @ stop={sl:.2f}")
                    except Exception as e:
                        logger.warning(f"Failed to place crypto SL: {e}")

                    # Place take-profit limit order
                    try:
                        tp_req = LimitOrderRequest(
                            symbol=alpaca_symbol,
                            qty=filled_qty,
                            side=OrderSide.SELL,
                            limit_price=round(tp, 2),
                            time_in_force=TimeInForce.GTC,
                        )
                        self.trading.submit_order(tp_req)
                        logger.info(f"CRYPTO TP: {filled_qty} {alpaca_symbol} @ limit={tp:.2f}")
                    except Exception as e:
                        logger.warning(f"Failed to place crypto TP: {e}")

                    return TradeResult(symbol, direction, filled_qty, filled_price, sl, tp, conf,
                                       True, f"Crypto: {filled_qty:.4f} units, SL/TP placed")
                else:
                    status = filled_order.status if hasattr(filled_order, 'status') else 'unknown'
                    logger.warning(f"Crypto order status: {status}")
                    return TradeResult(symbol, direction, 0, entry, sl, tp, conf,
                                       True, f"Crypto order submitted (status={status})")
            else:
                # Stocks/ETFs: whole shares with bracket order for auto SL/TP
                qty = max(1, round(shares))
                # Fetch latest price to align SL/TP with current market
                try:
                    pos = self.get_open_positions()
                    latest_price = float(self.trading.get_last_quote(alpaca_symbol).ask_price or
                                         self.trading.get_last_trade(alpaca_symbol).price)
                    if direction == 'SELL':
                        tp = min(tp, latest_price - 0.01)
                        sl = max(sl, latest_price + 0.01)
                        if tp >= sl:
                            return TradeResult(symbol, direction, qty, entry, sl, tp, conf,
                                               False, "SL/TP too tight after price move")
                    else:
                        tp = max(tp, latest_price + 0.01)
                        sl = min(sl, latest_price - 0.01)
                        if tp <= sl:
                            return TradeResult(symbol, direction, qty, entry, sl, tp, conf,
                                               False, "SL/TP too tight after price move")
                except Exception:
                    pass
                precision = 4 if tp < 1.0 else 2
                # Swing trades (1d) use GTC and 2x wider SL/TP to absorb daily volatility
                tif = TimeInForce.GTC if interval == '1d' else TimeInForce.DAY
                order = MarketOrderRequest(
                    symbol=alpaca_symbol,
                    qty=qty,
                    side=side,
                    time_in_force=tif,
                    order_class=OrderClass.BRACKET,
                    take_profit={'limit_price': round(tp, precision)},
                    stop_loss={'stop_price': round(sl, precision)},
                )
                self.trading.submit_order(order)
                logger.info(f"BRACKET {direction} {qty} {alpaca_symbol} @ ~{entry:.2f} | "
                            f"SL={sl:.2f} TP={tp:.2f} | tif={tif.value} | interval={interval}")
                return TradeResult(symbol, direction, qty, entry, sl, tp, conf,
                                   True, f"Bracket ({interval}): {direction} {qty} sh")

        except Exception as e:
            logger.error(f"Order failed for {symbol}: {e}")
            return TradeResult(symbol, direction, shares, entry, sl, tp, conf,
                               False, str(e))

    @staticmethod
    def _widen_sl_tp_for_swing(entry: float, sl: float, tp: float, direction: str) -> tuple[float, float]:
        """Widen SL/TP for 1d swing trades.

        Strategies built for 1h produce tight 0.5%/1% levels. For daily bars
        that would be stopped out by intraday noise. We expand to a floor of
        1.5% SL and 3% TP, preserving the original risk/reward ratio.
        """
        if direction == 'BUY':
            sl_pct = abs(entry - sl) / entry if entry > 0 else 0
            tp_pct = abs(tp - entry) / entry if entry > 0 else 0
            if sl_pct < 0.015 or tp_pct < 0.03:
                new_sl = entry * (1 - 0.015)
                new_tp = entry * (1 + 0.03) if tp_pct >= sl_pct else entry * (1 + 0.03)
                return new_sl, new_tp
        elif direction == 'SELL':
            sl_pct = abs(sl - entry) / entry if entry > 0 else 0
            tp_pct = abs(entry - tp) / entry if entry > 0 else 0
            if sl_pct < 0.015 or tp_pct < 0.03:
                new_sl = entry * (1 + 0.015)
                new_tp = entry * (1 - 0.03)
                return new_sl, new_tp
        return sl, tp

    def close_position(self, symbol: str) -> TradeResult:
        try:
            alpaca_symbol = _to_alpaca_symbol(symbol)
            positions = self.trading.get_all_positions()
            pos = None
            for p in positions:
                if p.symbol == alpaca_symbol or p.symbol == alpaca_symbol.replace('/', ''):
                    pos = p
                    break
            if pos is None:
                return TradeResult(symbol, 'CLOSE', 0, 0, 0, 0, 0, False,
                                   f"No open position for {symbol}")
            actual_symbol = pos.symbol
            qty = float(pos.qty)
            side = OrderSide.SELL if qty > 0 else OrderSide.BUY
            qty = abs(qty)

            order = MarketOrderRequest(
                symbol=actual_symbol,
                qty=qty,
                side=side,
                time_in_force=TimeInForce.GTC,
            )
            self.trading.submit_order(order)
            logger.info(f"CLOSE {actual_symbol}: {side.value} {qty}")
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
        """Get closed trades with calculated P&L.

        Alpaca flattens bracket orders into 3 separate orders (entry MARKET,
        TP LIMIT, SL STOP). We pair them heuristically: for each filled MARKET
        order, find the next filled order of opposite side with matching qty
        within a 24h window.
        """
        from datetime import datetime, timedelta
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus

        after = datetime.now() - timedelta(days=days)
        req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=500, after=after)
        orders = self.trading.get_orders(filter=req)

        filled = []
        for o in orders:
            if o.filled_avg_price is None or float(o.filled_qty or 0) <= 0:
                continue
            filled.append({
                'symbol': o.symbol,
                'side': str(o.side),
                'qty': float(o.filled_qty or o.qty or 0),
                'price': float(o.filled_avg_price),
                'type': str(o.type),
                'filled_at': o.filled_at,
            })

        by_symbol: dict[str, list[dict]] = {}
        for o in filled:
            by_symbol.setdefault(o['symbol'], []).append(o)
        for sym in by_symbol:
            by_symbol[sym].sort(key=lambda x: x['filled_at'])

        trades = []
        for sym, lst in by_symbol.items():
            i = 0
            while i < len(lst):
                entry = lst[i]
                exit_ord = None
                exit_idx = -1
                for j in range(i + 1, len(lst)):
                    cand = lst[j]
                    if cand['side'] == entry['side']:
                        continue
                    qty_ref = max(entry['qty'], 1e-9)
                    if abs(cand['qty'] - entry['qty']) / qty_ref > 0.05:
                        continue
                    delta_s = (cand['filled_at'] - entry['filled_at']).total_seconds()
                    if delta_s > 86400 or delta_s < 0:
                        continue
                    exit_ord = cand
                    exit_idx = j
                    break

                if exit_ord is None:
                    i += 1
                    continue

                is_long = 'BUY' in entry['side']
                if is_long:
                    pnl = (exit_ord['price'] - entry['price']) * entry['qty']
                    pnl_pct = (exit_ord['price'] - entry['price']) / entry['price'] * 100
                else:
                    pnl = (entry['price'] - exit_ord['price']) * entry['qty']
                    pnl_pct = (entry['price'] - exit_ord['price']) / entry['price'] * 100

                if 'LIMIT' in exit_ord['type']:
                    exit_type = 'TP'
                elif 'STOP' in exit_ord['type']:
                    exit_type = 'SL'
                else:
                    exit_type = 'manual'

                duration_min = (exit_ord['filled_at'] - entry['filled_at']).total_seconds() / 60

                trades.append({
                    'symbol': sym,
                    'side': entry['side'].replace('OrderSide.', ''),
                    'qty': entry['qty'],
                    'entry': round(entry['price'], 4),
                    'exit': round(exit_ord['price'], 4),
                    'pnl': round(pnl, 2),
                    'pnl_pct': round(pnl_pct, 2),
                    'entry_at': entry['filled_at'].isoformat(),
                    'exit_at': exit_ord['filled_at'].isoformat(),
                    'duration_min': round(duration_min, 1),
                    'exit_type': exit_type,
                })
                i = exit_idx + 1

        return sorted(trades, key=lambda t: t['entry_at'])

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
