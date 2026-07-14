"""
Signal Manager Module
======================
Logs signals to CSV, retrieves history, and formats output.
"""

import csv
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from config.settings import SIGNALS_LOG_FILE
from signals.generator import Signal

logger = logging.getLogger(__name__)

_CSV_HEADERS = [
    'timestamp', 'strategy', 'ticker', 'interval', 'direction',
    'entry_price', 'stop_loss', 'take_profit', 'confidence',
    'risk_reward', 'ml_filtered', 'ml_confidence',
    'ensemble_consensus', 'news_sentiment', 'confluence_score',
]


class SignalManager:
    """Manages signal logging, history, and formatting."""

    def __init__(self, log_file: Path = SIGNALS_LOG_FILE):
        self.log_file = log_file
        self._ensure_csv_exists()

    def _ensure_csv_exists(self) -> None:
        """Create CSV with headers if it doesn't exist or is empty.
        Migrates old-format CSVs (missing columns) to current format.
        """
        if not self.log_file.exists() or self.log_file.stat().st_size == 0:
            with open(self.log_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(_CSV_HEADERS)
            return

        # Check if CSV header matches current format; migrate if stale
        with open(self.log_file, 'r', newline='') as f:
            reader = csv.reader(f)
            try:
                existing_header = next(reader)
            except StopIteration:
                existing_header = []

        if existing_header == _CSV_HEADERS:
            return  # already up-to-date

        missing = [c for c in _CSV_HEADERS if c not in existing_header]
        logger.info(f"Migrating {self.log_file.name}: adding {len(missing)} missing columns {missing}")

        rows: list[dict[str, str]] = []
        with open(self.log_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                new_row = {h: row.get(h, '') for h in _CSV_HEADERS}
                rows.append(new_row)

        with open(self.log_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_HEADERS)
            writer.writeheader()
            writer.writerows(rows)

        logger.info(f"Migrated {self.log_file.name}: {len(rows)} rows, {len(_CSV_HEADERS)} columns")

    def _is_duplicate(self, signal: Signal, window_hours: int = 4) -> bool:
        """Check if same ticker+direction+entry_price was logged recently.

        Args:
            signal: Signal to check for duplicates.
            window_hours: Hours to look back (4 for 1h, 24 for 1d).

        Returns:
            True if duplicate found (should skip logging).
        """
        if not self.log_file.exists():
            return False

        try:
            # Read last 50 lines only (fast, avoids parsing entire CSV)
            lines = []
            with open(self.log_file, 'r') as f:
                all_lines = f.readlines()
                lines = all_lines[-50:] if len(all_lines) > 50 else all_lines[1:]  # skip header

            if not lines:
                return False

            cutoff = datetime.now() - timedelta(hours=window_hours)
            target_entry = round(signal.entry_price, 2)

            for line in reversed(lines):
                try:
                    row = next(csv.reader([line.strip()]))
                    if len(row) < 6:
                        continue

                    ts_str, _, ticker, _, direction, entry_str = row[:6]

                    # Parse timestamp
                    ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    if ts < cutoff:
                        break  # older than window, stop searching

                    # Match: same ticker + same direction + similar entry price
                    if (ticker == signal.ticker
                            and direction == signal.direction
                            and abs(round(float(entry_str), 2) - target_entry) < 0.01):
                        logger.debug(f"Dedup: {signal.ticker} {signal.direction} "
                                     f"@ ${signal.entry_price:.2f} already logged at {ts_str}")
                        return True
                except (ValueError, StopIteration):
                    continue

        except Exception as e:
            logger.debug(f"Dedup check failed: {e}")

        return False

    def log_signal(self, signal: Signal, window_hours: int = 4) -> bool:
        """Append a signal to the CSV log (with dedup).

        Args:
            signal: Signal object to log.
            window_hours: Hours to look back for dedup (4 for 1h, 24 for 1d).

        Returns:
            True if logged, False if deduped.
        """
        if self._is_duplicate(signal, window_hours):
            logger.info(f"Dedup: skipping {signal.direction} {signal.ticker} "
                        f"@ ${signal.entry_price:.2f} (already logged recently)")
            return False

        row = signal.to_dict()
        with open(self.log_file, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_HEADERS)
            writer.writerow(row)
        logger.info(f"Signal logged: {signal.direction} {signal.ticker} @ {signal.entry_price:.2f}")
        return True

    def get_history(self, ticker: str | None = None, n: int = 20) -> pd.DataFrame:
        """Get the last N signals from the log.

        Args:
            ticker: Filter by ticker (None = all).
            n: Number of recent signals to return.

        Returns:
            DataFrame with signal history.
        """
        if not self.log_file.exists():
            return pd.DataFrame(columns=_CSV_HEADERS)

        df = pd.read_csv(self.log_file, on_bad_lines='warn')
        if ticker:
            df = df[df['ticker'] == ticker]
        return df.tail(n)

    @staticmethod
    def format_signal(signal: Signal) -> str:
        """Format a signal for terminal display.

        Args:
            signal: Signal object.

        Returns:
            Formatted string.
        """
        if signal.direction == 'HOLD':
            return (
                f"\n{'='*50}\n"
                f"  SIGNAL: HOLD - No action\n"
                f"  Strategy: {signal.strategy}\n"
                f"  Ticker: {signal.ticker} ({signal.interval})\n"
                f"  Price: ${signal.entry_price:,.2f}\n"
                f"  Time: {signal.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"{'='*50}"
            )

        direction_icon = 'UP' if signal.direction == 'BUY' else 'DOWN'
        rr = signal.risk_reward_ratio
        rr_str = f"{rr:.1f}" if rr else "N/A"

        lines = [
            "",
            "=" * 50,
            f"  SIGNAL: {signal.direction} {direction_icon}",
            f"  Strategy: {signal.strategy}",
            f"  Ticker: {signal.ticker} ({signal.interval})",
            "-" * 50,
            f"  Entry Price:    ${signal.entry_price:>12,.2f}",
            f"  Stop Loss:      ${signal.stop_loss:>12,.2f}",
            f"  Take Profit:    ${signal.take_profit:>12,.2f}",
            f"  Risk/Reward:    {rr_str:>12}",
            f"  Confidence:     {signal.confidence:>12.1%}",
            "-" * 50,
        ]

        if signal.ml_filtered:
            ml_conf = f"{signal.ml_confidence:.1%}" if signal.ml_confidence else "N/A"
            lines.append(f"  ML Filter:      {'PASS' if signal.direction != 'HOLD' else 'REJECT':>12}")
            lines.append(f"  ML Confidence:  {ml_conf:>12}")
            lines.append("-" * 50)

        lines.append(f"  Time: {signal.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 50)

        return "\n".join(lines)

    @staticmethod
    def format_history(df: pd.DataFrame) -> str:
        """Format signal history for terminal display.

        Args:
            df: DataFrame from get_history().

        Returns:
            Formatted string.
        """
        if df.empty:
            return "\n  No signals in history."

        lines = [
            "",
            f"  {'Timestamp':<20} {'Ticker':<10} {'Strategy':<14} {'Signal':<6} {'Price':>10} {'Conf':>6}",
            "  " + "-" * 70,
        ]
        for _, row in df.iterrows():
            ts = str(row['timestamp'])[:19]
            lines.append(
                f"  {ts:<20} {row['ticker']:<10} {row['strategy']:<14} "
                f"{row['direction']:<6} ${row['entry_price']:>9,.2f} {row['confidence']:>5.0%}"
            )
        return "\n".join(lines)
