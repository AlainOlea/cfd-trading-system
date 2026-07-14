"""
Signal accuracy report: which strategies/tickers/hours/days actually win.

Joins closed Alpaca paper trades against logs/signals.csv (matching each
trade to the signal that most likely triggered it: same ticker, same
direction, most recent signal before entry within --match-hours) so we can
break win rate and P&L down by strategy, ticker, hour of day (ET), and day
of week — the same cut we did manually once; this makes it repeatable so we
can check whether the patterns (e.g. macd_vwap >> rsi_bb) hold as more
trades accumulate.

Usage:
    python3 scripts/signal_accuracy_report.py
    python3 scripts/signal_accuracy_report.py --days 60 --csv results/signal_accuracy.csv
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import click
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from signals.alpaca_broker import AlpacaBroker, _normalize_symbol  # noqa: E402

SIGNALS_LOG = ROOT / 'logs' / 'signals.csv'
VALID_INTERVALS = ('1m', '1h', '1d')
VALID_DIRECTIONS = ('BUY', 'SELL')


def load_signals() -> pd.DataFrame:
    """Load logs/signals.csv, keeping only well-formed actionable rows."""
    sig = pd.read_csv(SIGNALS_LOG, on_bad_lines='skip')
    sig = sig[sig['interval'].isin(VALID_INTERVALS) & sig['direction'].isin(VALID_DIRECTIONS)].copy()
    sig['timestamp'] = pd.to_datetime(sig['timestamp'], errors='coerce')
    sig = sig.dropna(subset=['timestamp']).sort_values('timestamp')
    return sig


def match_trade_to_signal(trade: pd.Series, sig: pd.DataFrame, match_hours: int) -> dict:
    """Find the closest signal before this trade's entry (same symbol + direction)."""
    target = _normalize_symbol(trade['symbol'])
    direction = trade['side'].replace('OrderSide.', '')
    entry_at = trade['entry_at']

    cands = sig[
        (sig['ticker'].apply(_normalize_symbol) == target)
        & (sig['direction'] == direction)
        & (sig['timestamp'] <= entry_at)
        & (sig['timestamp'] >= entry_at - timedelta(hours=match_hours))
    ]
    if cands.empty:
        return {'strategy': None, 'confidence': None, 'confluence_score': None}
    best = cands.iloc[-1]
    return {
        'strategy': best['strategy'],
        'confidence': best['confidence'],
        'confluence_score': best['confluence_score'],
    }


def build_report(days: int, match_hours: int) -> pd.DataFrame:
    broker = AlpacaBroker()
    if not broker.is_configured:
        raise click.ClickException("ALPACA_API_KEY not set in .env")

    trades = pd.DataFrame(broker.get_trade_history(days=days))
    if trades.empty:
        raise click.ClickException(f"No closed trades in the last {days} days.")
    trades['entry_at'] = pd.to_datetime(trades['entry_at']).dt.tz_convert(None)

    sig = load_signals()

    rows = []
    for _, t in trades.iterrows():
        match = match_trade_to_signal(t, sig, match_hours)
        row = t.to_dict()
        row.update(match)
        row['win'] = row['pnl'] > 0
        entry_et = t['entry_at'].tz_localize('UTC').tz_convert('America/New_York')
        row['hour_et'] = entry_et.hour
        row['dow_et'] = entry_et.day_name()
        rows.append(row)

    return pd.DataFrame(rows)


def _print_group(df: pd.DataFrame, by: str, title: str) -> None:
    g = df.groupby(by, dropna=False).agg(
        trades=('pnl', 'size'), win_rate=('win', 'mean'), total_pnl=('pnl', 'sum'),
    ).sort_values('total_pnl', ascending=False)
    click.echo(f"\n  {title}")
    click.echo(f"  {'-' * 50}")
    click.echo(f"  {'':<12} {'trades':>7} {'win%':>7} {'P&L':>10}")
    for idx, r in g.iterrows():
        label = str(idx) if pd.notna(idx) else '(no match)'
        click.echo(f"  {label:<12} {int(r['trades']):>7} {r['win_rate']*100:>6.1f}% {r['total_pnl']:>+10.2f}")


@click.command()
@click.option('--days', default=90, type=int, help='Days of closed-trade history to pull from Alpaca')
@click.option('--match-hours', default=6, type=int, help='Window to match a trade back to its signal')
@click.option('--csv', 'csv_path', type=click.Path(), default=None,
              help='Export the full per-trade merged table (e.g. results/signal_accuracy.csv)')
def main(days: int, match_hours: int, csv_path: str | None) -> None:
    """Break down closed-trade win rate/P&L by strategy, ticker, hour, and day."""
    df = build_report(days, match_hours)
    matched = df['strategy'].notna().sum()

    click.echo(f"\n  SIGNAL ACCURACY REPORT (last {days}d, {len(df)} closed trades)")
    click.echo(f"  {'=' * 50}")
    click.echo(f"  Matched to a source signal: {matched}/{len(df)} (within {match_hours}h)")
    win_rate = df['win'].mean() * 100
    click.echo(f"  Overall win rate: {win_rate:.1f}%   Total P&L: ${df['pnl'].sum():+.2f}")

    _print_group(df, 'strategy', 'By strategy')
    _print_group(df, 'symbol', 'By ticker')
    _print_group(df, 'hour_et', 'By hour of entry (ET)')
    _print_group(df, 'dow_et', 'By day of week (ET)')

    click.echo(f"\n  {'-' * 50}")
    click.echo("  Sample size caveat: breakdowns with < ~10 trades per bucket are")
    click.echo("  directional, not statistically significant — re-run periodically")
    click.echo("  and watch whether the ranking is stable as trades accumulate.\n")

    if csv_path:
        df.to_csv(csv_path, index=False)
        click.echo(f"  Exported {len(df)} rows -> {csv_path}\n")


if __name__ == '__main__':
    main()
