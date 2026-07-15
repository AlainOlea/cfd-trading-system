"""
One-shot migration: logs/signals.csv -> logs/signals.db (SignalStore).

Imports the historical CSV signal log into the SQLite store so the replay
script (scripts/replay_signals.py) can evaluate old signals too. Safe to
re-run: rows already imported (matched on ts+ticker+interval+direction)
are skipped.

Usage:
    source venv/bin/activate
    python3 scripts/migrate_signals_csv_to_db.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config.settings import SIGNALS_LOG_FILE
from signals.store import SignalStore


def main() -> None:
    if not SIGNALS_LOG_FILE.exists():
        print(f"No CSV found at {SIGNALS_LOG_FILE}")
        return

    df = pd.read_csv(SIGNALS_LOG_FILE)
    store = SignalStore()

    existing = {
        (r['ts'], r['ticker'], r['interval'], r['direction'])
        for r in store.query('SELECT ts, ticker, interval, direction FROM signals')
    }

    imported = skipped = 0
    for _, row in df.iterrows():
        key = (str(row['timestamp']), str(row['ticker']),
               str(row['interval']), str(row['direction']))
        if key in existing:
            skipped += 1
            continue

        def _num(v):
            try:
                f = float(v)
                return f if f == f else None  # NaN -> None
            except (TypeError, ValueError):
                return None

        stars = _num(row.get('confluence_score'))
        store._insert('signals', {
            'ts': str(row['timestamp']),
            'run_id': 'csv-migration',
            'ticker': str(row['ticker']),
            'interval': str(row['interval']),
            'strategy': str(row.get('strategy', '')),
            'direction': str(row['direction']),
            'entry_price': _num(row.get('entry_price')),
            'stop_loss': _num(row.get('stop_loss')),
            'take_profit': _num(row.get('take_profit')),
            'confidence': _num(row.get('confidence')),
            'ml_confidence': _num(row.get('ml_confidence')),
            'stars_total': int(stars) if stars is not None else None,
            'skip_reason': '',
            'extras': '',
        })
        imported += 1

    print(f"Imported {imported} rows, skipped {skipped} already-present rows")
    print(f"DB: {store.db_file}")


if __name__ == '__main__':
    main()
