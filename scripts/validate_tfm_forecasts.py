"""
TimesFM Forecast Validation — forecast de 60 min vs velas 1min reales.
======================================================================
Para cada forecast guardado en tfm_forecasts (logs/signals.db) cuya ventana
de 60 minutos ya transcurrió, compara contra data/raw/{TICKER}_1m.csv:

- Dirección: ¿el signo de (precio_real_60min - precio_inicial) coincidió?
- Orden de extremos: ¿el mínimo real llegó antes que el máximo real, como
  predijo el modelo? (min_first) — audita la asimetría SL(t=1)/TP(t=60).
- MAE %: error absoluto medio del path pronosticado vs el real.
- Cobertura de banda: % de minutos reales dentro de [q10, q80].

Usage:
    source venv/bin/activate
    python3 scripts/validate_tfm_forecasts.py
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from config.settings import RAW_DATA_DIR
from signals.store import SignalStore

_1m_cache: dict[str, pd.DataFrame | None] = {}


def _load_1m(ticker: str) -> pd.DataFrame | None:
    if ticker not in _1m_cache:
        path = RAW_DATA_DIR / f"{ticker}_1m.csv"
        _1m_cache[ticker] = (
            pd.read_csv(path, parse_dates=['datetime'], index_col='datetime').sort_index()
            if path.exists() else None
        )
    return _1m_cache[ticker]


def _to_utc_naive(ts_str: str) -> datetime | None:
    try:
        ts = datetime.fromisoformat(ts_str)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.astimezone()
    return ts.astimezone(timezone.utc).replace(tzinfo=None)


def validate(row: dict) -> dict | None:
    fc = json.loads(row['forecast']) if row['forecast'] else []
    if len(fc) < 10:
        return None
    df = _load_1m(row['ticker'])
    if df is None:
        return None
    start = _to_utc_naive(row['ts'])
    if start is None:
        return None
    horizon = len(fc)
    window = df.loc[(df.index > start) & (df.index <= start + timedelta(minutes=horizon + 5))]
    if len(window) < horizon * 0.5:  # need at least half the window (gaps/market close)
        return None

    actual = window['close'].to_numpy()[:horizon]
    n = len(actual)
    fc_arr = np.asarray(fc[:n])
    last = row['last_price'] or fc_arr[0]

    actual_dir = int(np.sign(actual[-1] - last))
    dir_hit = int(actual_dir == row['direction']) if actual_dir != 0 else None

    actual_min_first = int(int(np.argmin(actual)) < int(np.argmax(actual)))
    order_hit = int(actual_min_first == row['min_first']) if row['min_first'] is not None else None

    mae_pct = float(np.mean(np.abs(fc_arr - actual)) / last * 100)

    coverage = None
    if row['q10'] and row['q80']:
        q10 = np.asarray(json.loads(row['q10'])[:n])
        q80 = np.asarray(json.loads(row['q80'])[:n])
        coverage = float(np.mean((actual >= q10) & (actual <= q80)) * 100)

    return {'dir_hit': dir_hit, 'order_hit': order_hit,
            'mae_pct': mae_pct, 'coverage': coverage, 'n': n}


def main() -> None:
    store = SignalStore()
    rows = store.query('SELECT * FROM tfm_forecasts ORDER BY ts')
    print(f"Forecasts almacenados: {len(rows)}")

    results = []
    for r in rows:
        v = validate(r)
        if v:
            v['ticker'] = r['ticker']
            results.append(v)
    if not results:
        print("Ninguno validable aún (ventana de 60 min sin transcurrir o sin datos 1m).")
        return

    df = pd.DataFrame(results)
    print(f"Validados: {len(df)}\n")
    print(f"{'ticker':<9}{'N':>4}{'dir%':>7}{'orden%':>8}{'MAE%':>7}{'banda%':>8}")
    for tk, g in df.groupby('ticker'):
        d = g['dir_hit'].dropna()
        o = g['order_hit'].dropna()
        print(f"{tk:<9}{len(g):>4}"
              f"{(d.mean() * 100 if len(d) else float('nan')):>7.1f}"
              f"{(o.mean() * 100 if len(o) else float('nan')):>8.1f}"
              f"{g['mae_pct'].mean():>7.3f}"
              f"{g['coverage'].dropna().mean() if g['coverage'].notna().any() else float('nan'):>8.1f}")
    d_all = df['dir_hit'].dropna()
    o_all = df['order_hit'].dropna()
    print(f"\nTOTAL: dirección {d_all.mean()*100:.1f}% ({len(d_all)}) | "
          f"orden min/max {o_all.mean()*100:.1f}% ({len(o_all)}) | "
          f"MAE {df['mae_pct'].mean():.3f}%")
    print("\nInterpretación: si 'orden%' es bajo, la asimetría SL(t=1)/TP(t=60)")
    print("de los brackets basados en TimesFM está temporalmente mal fundada.")


if __name__ == '__main__':
    main()
