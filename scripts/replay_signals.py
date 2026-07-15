"""
Signal Replay — resolve historical signals against 1-minute data.
=================================================================
For every BUY/SELL signal in logs/signals.db (traded or not), walks the
1-minute candles in data/raw/{TICKER}_1m.csv forward from the signal
timestamp and determines which level was touched first: take-profit (win)
or stop-loss (loss). Results are stored in the replay_results table and an
aggregate reliability report is printed (by strategy, stars, ticker, and
traded vs not-traded).

This answers: "would the signals we did NOT trade have been winners?"

Conventions:
- Signal timestamps are naive local time; 1m CSVs are UTC. Conversion uses
  the host's local timezone (both are produced on this machine).
- If both SL and TP fall within the same 1m candle's high-low range, the
  outcome is counted as SL (conservative).
- Resolution window: end of the signal's trading day for 1h/1m signals,
  10 trading days for 1d signals. Unresolved = neither level touched.

Usage:
    source venv/bin/activate
    python3 scripts/replay_signals.py            # replay new signals + report
    python3 scripts/replay_signals.py --report   # report only, no new replay
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config.settings import RAW_DATA_DIR
from signals.store import SignalStore

RESOLUTION_DAYS = {'1d': 10}   # trading-day window per interval
DEFAULT_SAME_DAY = True        # 1h/1m resolve by end of signal's UTC day

_1m_cache: dict[str, pd.DataFrame | None] = {}


def _load_1m(ticker: str) -> pd.DataFrame | None:
    if ticker not in _1m_cache:
        path = RAW_DATA_DIR / f"{ticker}_1m.csv"
        if not path.exists():
            _1m_cache[ticker] = None
        else:
            df = pd.read_csv(path, parse_dates=['datetime'], index_col='datetime')
            _1m_cache[ticker] = df.sort_index()
    return _1m_cache[ticker]


def _to_utc(ts_str: str) -> datetime | None:
    """Naive local signal timestamp -> naive UTC (to match 1m CSV index)."""
    try:
        ts = datetime.fromisoformat(ts_str)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.astimezone()  # attach host-local tz
    return ts.astimezone(timezone.utc).replace(tzinfo=None)


def replay_signal(sig: dict) -> dict | None:
    """Resolve one signal against 1m data. Returns replay row or None if unpriceable."""
    entry = sig.get('entry_price') or 0
    sl = sig.get('stop_loss') or 0
    tp = sig.get('take_profit') or 0
    if entry <= 0 or sl <= 0 or tp <= 0 or sl == tp:
        return None

    df = _load_1m(sig['ticker'])
    if df is None:
        return None

    start = _to_utc(sig['ts'])
    if start is None:
        return None

    is_buy = sig['direction'] == 'BUY'
    # Sanity: SL must be on the losing side of entry
    if is_buy and not (sl < entry < tp):
        return None
    if not is_buy and not (tp < entry < sl):
        return None

    if sig['interval'] == '1d':
        end = start + timedelta(days=RESOLUTION_DAYS['1d'] * 1.5)  # calendar buffer
    else:
        end = start.replace(hour=23, minute=59, second=59)

    window = df.loc[(df.index > start) & (df.index <= end)]
    if window.empty:
        return None

    outcome, bars, resolved_at = 'unresolved', len(window), ''
    max_fav = max_adv = 0.0
    for i, (ts, row) in enumerate(window.iterrows(), start=1):
        hi, lo = float(row['high']), float(row['low'])
        if is_buy:
            max_fav = max(max_fav, (hi - entry) / entry * 100)
            max_adv = min(max_adv, (lo - entry) / entry * 100)
            hit_sl, hit_tp = lo <= sl, hi >= tp
        else:
            max_fav = max(max_fav, (entry - lo) / entry * 100)
            max_adv = min(max_adv, (entry - hi) / entry * 100)
            hit_sl, hit_tp = hi >= sl, lo <= tp
        if hit_sl:  # SL first when both hit in same candle (conservative)
            outcome, bars, resolved_at = 'SL', i, ts.isoformat()
            break
        if hit_tp:
            outcome, bars, resolved_at = 'TP', i, ts.isoformat()
            break

    if outcome == 'TP':
        pnl_pct = abs(tp - entry) / entry * 100
    elif outcome == 'SL':
        pnl_pct = -abs(sl - entry) / entry * 100
    else:
        last_close = float(window.iloc[-1]['close'])
        pnl_pct = ((last_close - entry) if is_buy else (entry - last_close)) / entry * 100

    return {
        'outcome': outcome,
        'bars_to_resolution': bars,
        'pnl_pct': round(pnl_pct, 4),
        'max_favorable_pct': round(max_fav, 4),
        'max_adverse_pct': round(max_adv, 4),
        'resolved_at': resolved_at,
    }


def run_replay(store: SignalStore) -> int:
    signals = store.get_signals(unreplayed_only=True)
    print(f"Replaying {len(signals)} unreplayed BUY/SELL signals...")
    done = skipped = 0
    for sig in signals:
        res = replay_signal(sig)
        if res is None:
            store.log_replay(sig['id'], 'skipped',
                             extras={'reason': 'no data / invalid levels'})
            skipped += 1
            continue
        store.log_replay(sig['id'], res['outcome'],
                         bars_to_resolution=res['bars_to_resolution'],
                         pnl_pct=res['pnl_pct'],
                         max_favorable_pct=res['max_favorable_pct'],
                         max_adverse_pct=res['max_adverse_pct'],
                         resolved_at=res['resolved_at'])
        done += 1
    print(f"Replayed {done}, skipped {skipped} (no 1m data or invalid SL/TP)")
    return done


def _print_group(store: SignalStore, label: str, group_expr: str,
                 where: str = '') -> None:
    rows = store.query(f"""
        SELECT {group_expr} AS grp,
               COUNT(*) AS n,
               SUM(CASE WHEN r.outcome = 'TP' THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN r.outcome = 'SL' THEN 1 ELSE 0 END) AS losses,
               SUM(CASE WHEN r.outcome = 'unresolved' THEN 1 ELSE 0 END) AS open_,
               ROUND(AVG(r.pnl_pct), 3) AS avg_pnl,
               ROUND(SUM(r.pnl_pct), 2) AS tot_pnl
        FROM replay_results r JOIN signals s ON s.id = r.signal_id
        WHERE r.outcome != 'skipped' {('AND ' + where) if where else ''}
        GROUP BY grp ORDER BY tot_pnl DESC
    """)
    print(f"\n  {label}")
    print(f"  {'Group':<22} {'N':>5} {'TP':>5} {'SL':>5} {'Unres':>6} "
          f"{'Win%':>6} {'AvgPnL%':>8} {'TotPnL%':>8}")
    for r in rows:
        resolved = (r['wins'] or 0) + (r['losses'] or 0)
        wr = (r['wins'] / resolved * 100) if resolved else 0.0
        print(f"  {str(r['grp']):<22} {r['n']:>5} {r['wins']:>5} {r['losses']:>5} "
              f"{r['open_']:>6} {wr:>5.1f}% {r['avg_pnl'] or 0:>8} {r['tot_pnl'] or 0:>8}")


def print_report(store: SignalStore) -> None:
    print("\n" + "=" * 70)
    print("  SIGNAL REPLAY RELIABILITY REPORT")
    print("=" * 70)
    _print_group(store, "By strategy:", "s.strategy")
    _print_group(store, "By confluence stars:", "COALESCE(s.stars_total, 'n/a')")
    _print_group(store, "By ticker:", "s.ticker")
    _print_group(store, "Traded vs not traded:",
                 "CASE WHEN s.trade_placed = 1 THEN 'traded' ELSE 'not_traded' END")
    _print_group(store, "By interval:", "s.interval")


def main() -> None:
    store = SignalStore()
    if '--report' not in sys.argv:
        run_replay(store)
    print_report(store)


if __name__ == '__main__':
    main()
