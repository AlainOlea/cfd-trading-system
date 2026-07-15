"""
Signal Store Module
===================
SQLite-backed store for enriched signal logging: technical signal + ML
prediction + TimesFM forecast + star breakdown + trade decision.

Schema policy is ADDITIVE-ONLY: columns are declared in _SIGNALS_SCHEMA /
_REPLAY_SCHEMA dicts and auto-added via ALTER TABLE on open (mirroring the
CSV auto-migration in SignalManager._ensure_csv_exists). Columns are never
renamed or dropped. Experimental fields go in the `extras` JSON column and
get promoted to real columns once stable.
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from config.settings import LOGS_DIR

logger = logging.getLogger(__name__)

SIGNALS_DB_FILE = LOGS_DIR / 'signals.db'

# Additive-only schemas: {column: SQL type}. New columns may be appended;
# existing ones must never be renamed or removed.
_SIGNALS_SCHEMA: dict[str, str] = {
    'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
    'ts': 'TEXT',                 # ISO timestamp of signal evaluation
    'run_id': 'TEXT',             # groups all rows from one pipeline run
    'ticker': 'TEXT',
    'interval': 'TEXT',
    'strategy': 'TEXT',
    # Technical layer
    'direction': 'TEXT',          # BUY/SELL/HOLD (final_direction)
    'entry_price': 'REAL',
    'stop_loss': 'REAL',
    'take_profit': 'REAL',
    'confidence': 'REAL',
    # ML layer (XGBoost)
    'ml_direction': 'TEXT',
    'ml_confidence': 'REAL',
    'ml_vetoed': 'INTEGER',       # 1 if ML downgraded signal to HOLD
    # TimesFM layer
    'tfm_direction': 'TEXT',      # BUY/SELL ('' if no forecast)
    'tfm_agrees': 'INTEGER',
    'tfm_sl': 'REAL',
    'tfm_tp': 'REAL',
    # Star breakdown (why each star was earned)
    'stars_total': 'INTEGER',
    'star_base': 'INTEGER',
    'star_agree': 'INTEGER',      # multi-TF agreement OR ML confirms
    'star_ml_strong': 'INTEGER',  # ML confirms AND (multi-TF or >65% conviction)
    'star_conf': 'INTEGER',       # avg confidence >= 70%
    'star_tfm': 'INTEGER',        # TimesFM direction match bonus
    # Decision / outcome of this run
    'telegram_sent': 'INTEGER',
    'telegram_message': 'TEXT',   # full message text (kept even if send failed)
    'trade_placed': 'INTEGER',
    'skip_reason': 'TEXT',        # already_holding / cooldown / below_stars / broker error / ''
    # Experimental fields (JSON)
    'extras': 'TEXT',
}

_TFM_SCHEMA: dict[str, str] = {
    'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
    'ts': 'TEXT',                # when the forecast was made
    'run_id': 'TEXT',
    'ticker': 'TEXT',
    'last_price': 'REAL',        # price at forecast time
    'direction': 'INTEGER',      # +1 / -1 (sign of forecast[-1] - last_price)
    'confidence': 'REAL',
    # Temporal order of extremes within the 60-min forecast path:
    # if min_first=1 on a BUY, the model expects the dip BEFORE the rally —
    # key to auditing the SL-at-t=1 / TP-at-t=60 quantile asymmetry.
    'min_pos': 'INTEGER',        # index (0-59) of forecast minimum
    'max_pos': 'INTEGER',        # index of forecast maximum
    'min_first': 'INTEGER',
    'forecast': 'TEXT',          # JSON array, 60 floats (point forecast)
    'q10': 'TEXT',               # JSON array, 10th percentile path
    'q80': 'TEXT',               # JSON array, 80th percentile path
    'extras': 'TEXT',
}

_REPLAY_SCHEMA: dict[str, str] = {
    'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
    'signal_id': 'INTEGER',           # FK -> signals.id
    'outcome': 'TEXT',                # TP / SL / unresolved
    'bars_to_resolution': 'INTEGER',
    'pnl_pct': 'REAL',
    'max_favorable_pct': 'REAL',
    'max_adverse_pct': 'REAL',
    'resolved_at': 'TEXT',
    'replayed_at': 'TEXT',
    'extras': 'TEXT',
}


class SignalStore:
    """SQLite store for enriched signals and replay results."""

    def __init__(self, db_file: Path | None = None):
        # Resolved at call time (not def time) so tests can monkeypatch
        # signals.store.SIGNALS_DB_FILE to a temp path.
        self.db_file = db_file if db_file is not None else SIGNALS_DB_FILE
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        """Create tables and auto-add any missing columns (additive-only)."""
        with self._connect() as conn:
            for table, schema in (('signals', _SIGNALS_SCHEMA),
                                  ('replay_results', _REPLAY_SCHEMA),
                                  ('tfm_forecasts', _TFM_SCHEMA)):
                cols_sql = ', '.join(f'{c} {t}' for c, t in schema.items())
                conn.execute(f'CREATE TABLE IF NOT EXISTS {table} ({cols_sql})')

                existing = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
                missing = [c for c in schema if c not in existing]
                for col in missing:
                    conn.execute(f'ALTER TABLE {table} ADD COLUMN {col} {schema[col]}')
                if missing:
                    logger.info(f"SignalStore: migrated {table}, added columns {missing}")

    # ─── Writing ─────────────────────────────────────────────

    def log_result(self, result, *, run_id: str = '',
                   telegram_sent: bool = False,
                   trade_placed: bool = False,
                   skip_reason: str = '',
                   extras: dict[str, Any] | None = None) -> int:
        """Log a PipelineResult with full layer breakdown. Returns row id."""
        sig = result.technical_signal
        ml = result.ml_prediction or {}
        tfm = getattr(result, 'tfm_forecast', None) or {}

        ml_dir = ml.get('direction', '')
        ml_conf = ml.get('confidence')
        ml_vetoed = int(
            bool(ml_dir) and sig.direction != 'HOLD'
            and result.final_direction == 'HOLD'
        )

        breakdown = getattr(result, 'star_breakdown', None) or {}

        row = {
            'ts': result.timestamp.isoformat() if result.timestamp else datetime.now().isoformat(),
            'run_id': run_id,
            'ticker': result.ticker,
            'interval': result.interval,
            'strategy': sig.strategy,
            'direction': result.final_direction,
            'entry_price': sig.entry_price,
            'stop_loss': sig.stop_loss,
            'take_profit': sig.take_profit,
            'confidence': result.final_confidence,
            'ml_direction': ml_dir,
            'ml_confidence': ml_conf,
            'ml_vetoed': ml_vetoed,
            'tfm_direction': tfm.get('direction_label', ''),
            'tfm_agrees': int(bool(tfm.get('agrees'))) if tfm else None,
            'tfm_sl': tfm.get('sl'),
            'tfm_tp': tfm.get('tp'),
            'stars_total': result.confluence_score,
            'star_base': int(bool(breakdown.get('base'))),
            'star_agree': int(bool(breakdown.get('agree'))),
            'star_ml_strong': int(bool(breakdown.get('ml_strong'))),
            'star_conf': int(bool(breakdown.get('conf'))),
            'star_tfm': int(bool(breakdown.get('tfm'))),
            'telegram_sent': int(telegram_sent),
            'trade_placed': int(trade_placed),
            'skip_reason': skip_reason,
            'extras': json.dumps(extras) if extras else '',
        }
        return self._insert('signals', row)

    def update_decision(self, signal_id: int, *,
                        telegram_sent: bool | None = None,
                        telegram_message: str | None = None,
                        trade_placed: bool | None = None,
                        skip_reason: str | None = None) -> None:
        """Update decision fields on an already-logged signal."""
        sets, vals = [], []
        if telegram_sent is not None:
            sets.append('telegram_sent = ?'); vals.append(int(telegram_sent))
        if telegram_message is not None:
            sets.append('telegram_message = ?'); vals.append(telegram_message)
        if trade_placed is not None:
            sets.append('trade_placed = ?'); vals.append(int(trade_placed))
        if skip_reason is not None:
            sets.append('skip_reason = ?'); vals.append(skip_reason)
        if not sets:
            return
        vals.append(signal_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE signals SET {', '.join(sets)} WHERE id = ?", vals)

    def log_tfm_forecast(self, ticker: str, tfm: dict, *, run_id: str = '') -> int:
        """Persist a full TimesFM forecast (60-step path + quantile bands).

        `tfm` is the dict from TimesFMPredictor._build_result(): direction,
        forecast (np.ndarray), quantiles (60x10), confidence, last_price.
        """
        fc = tfm.get('forecast')
        q = tfm.get('quantiles')
        fc_list = [round(float(x), 6) for x in fc] if fc is not None else []
        min_pos = max_pos = None
        min_first = None
        if fc_list:
            min_pos = int(min(range(len(fc_list)), key=fc_list.__getitem__))
            max_pos = int(max(range(len(fc_list)), key=fc_list.__getitem__))
            min_first = int(min_pos < max_pos)
        row = {
            'ts': datetime.now().isoformat(),
            'run_id': run_id,
            'ticker': ticker,
            'last_price': tfm.get('last_price'),
            'direction': tfm.get('direction'),
            'confidence': tfm.get('confidence'),
            'min_pos': min_pos,
            'max_pos': max_pos,
            'min_first': min_first,
            'forecast': json.dumps(fc_list),
            'q10': json.dumps([round(float(x), 6) for x in q[:, 1]]) if q is not None else '',
            'q80': json.dumps([round(float(x), 6) for x in q[:, 8]]) if q is not None else '',
            'extras': '',
        }
        return self._insert('tfm_forecasts', row)

    def log_replay(self, signal_id: int, outcome: str, *,
                   bars_to_resolution: int | None = None,
                   pnl_pct: float | None = None,
                   max_favorable_pct: float | None = None,
                   max_adverse_pct: float | None = None,
                   resolved_at: str = '',
                   extras: dict[str, Any] | None = None) -> int:
        """Log a replay result for a signal. Returns row id."""
        row = {
            'signal_id': signal_id,
            'outcome': outcome,
            'bars_to_resolution': bars_to_resolution,
            'pnl_pct': pnl_pct,
            'max_favorable_pct': max_favorable_pct,
            'max_adverse_pct': max_adverse_pct,
            'resolved_at': resolved_at,
            'replayed_at': datetime.now().isoformat(),
            'extras': json.dumps(extras) if extras else '',
        }
        return self._insert('replay_results', row)

    def _insert(self, table: str, row: dict[str, Any]) -> int:
        cols = ', '.join(row)
        placeholders = ', '.join('?' * len(row))
        with self._connect() as conn:
            cur = conn.execute(
                f'INSERT INTO {table} ({cols}) VALUES ({placeholders})',
                list(row.values()),
            )
            return cur.lastrowid

    # ─── Reading ─────────────────────────────────────────────

    def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Run an arbitrary read query, returning rows as dicts."""
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(sql, params)]

    def get_signals(self, *, ticker: str | None = None,
                    directions: tuple[str, ...] = ('BUY', 'SELL'),
                    unreplayed_only: bool = False) -> list[dict[str, Any]]:
        """Fetch signals, optionally only those without a replay result yet."""
        sql = 'SELECT s.* FROM signals s'
        where = [f"s.direction IN ({', '.join('?' * len(directions))})"]
        params: list[Any] = list(directions)
        if unreplayed_only:
            sql += ' LEFT JOIN replay_results r ON r.signal_id = s.id'
            where.append('r.id IS NULL')
        if ticker:
            where.append('s.ticker = ?')
            params.append(ticker)
        sql += ' WHERE ' + ' AND '.join(where) + ' ORDER BY s.ts'
        return self.query(sql, tuple(params))
