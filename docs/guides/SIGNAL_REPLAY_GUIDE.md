# Signal Replay Guide

**Status**: Active (2026-07-14)

## What it is

Two tools that together answer *"was the system right?"* using data instead of anecdotes:

1. **`signals/store.py` (`SignalStore`)** — SQLite store at `logs/signals.db`. Every
   pipeline run under `paper-trade` logs one row per evaluated ticker+interval (including
   HOLD) with the full layer breakdown: technical signal, XGBoost direction/confidence,
   TimesFM agreement, per-star rationale (`star_base` … `star_tfm`), whether Telegram was
   sent, whether the trade was placed, and the skip reason if not
   (`below_stars`, `below_confidence`, `cooldown`, `Already holding X`, broker errors).
2. **`scripts/replay_signals.py`** — resolves every BUY/SELL signal (traded or NOT)
   against the 1-minute candles in `data/raw/{TICKER}_1m.csv`: which was touched first,
   TP (win) or SL (loss)? Results land in the `replay_results` table and an aggregate
   reliability report prints win rate and P&L by strategy, stars, ticker, interval, and
   traded-vs-not-traded.

## Usage

```bash
source venv/bin/activate
python3 scripts/replay_signals.py            # replay unresolved signals + print report
python3 scripts/replay_signals.py --report   # print report only (no new replay work)
python3 scripts/migrate_signals_csv_to_db.py # one-shot: import legacy logs/signals.csv
```

Ad-hoc analysis is plain SQL:

```bash
sqlite3 logs/signals.db "SELECT s.strategy, r.outcome, COUNT(*)
  FROM signals s JOIN replay_results r ON r.signal_id = s.id
  GROUP BY 1, 2"
```

## Conventions & caveats

- Signal timestamps are naive **local** time; 1m CSVs are **UTC**. Conversion uses the
  host's local timezone (both files are produced on this machine).
- If SL and TP both fall inside the same 1-minute candle, the outcome counts as **SL**
  (conservative).
- Resolution window: end of the signal's UTC day for 1h/1m signals; ~10 trading days for
  1d. Neither touched → `unresolved` (P&L = mark-to-market at window end).
- `skipped` outcome = no 1m data for the ticker/date or invalid SL/TP levels (e.g. SL on
  the wrong side of entry). These are excluded from the report.
- Replay assumes the fill at the signal's `entry_price` — real fills differ (the NVDA
  2026-07-14 signal replayed from 203.77 but filled at 206.64). Outcomes matched real
  bracket-order results in validation (NVDA→SL, UNG→TP), but P&L magnitudes are
  approximations.

## Schema policy (SignalStore)

Additive-only: columns are declared in `_SIGNALS_SCHEMA` / `_REPLAY_SCHEMA` dicts in
`signals/store.py` and auto-added with `ALTER TABLE ADD COLUMN` on open. Never rename or
drop a column. Experimental fields go in the `extras` JSON column; promote them to real
columns once stable.
