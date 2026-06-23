"""
Fetch Metadata Tracker
=======================
Tracks last fetch timestamp per ticker+interval pair.
Persists to JSON file with atomic writes.
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from config.settings import FETCH_METADATA_FILE

logger = logging.getLogger(__name__)


class FetchMetadata:
    """Track last fetch timestamp per ticker+interval.

    Stores metadata in a JSON file to survive restarts.
    Uses atomic writes (write tmp + rename) to prevent corruption.

    Schema:
        {
            "SPY": {
                "1d": {"last_fetch": "2026-06-22T07:00:00", "rows": 250},
                "1h": {"last_fetch": "2026-06-22T16:00:00", "rows": 427}
            }
        }
    """

    def __init__(self, metadata_file: Path = None):
        self.file = metadata_file or FETCH_METADATA_FILE
        self._data = self._load()

    def get_last_fetch(self, ticker: str, interval: str) -> datetime | None:
        """Get last fetch timestamp for a ticker+interval.

        Args:
            ticker: Symbol (e.g. 'SPY', 'BTC-USD').
            interval: Data interval (e.g. '1d', '1h', '1m').

        Returns:
            Last fetch datetime (UTC) or None if never fetched.
        """
        entry = self._data.get(ticker, {}).get(interval)
        if not entry:
            return None
        try:
            return datetime.fromisoformat(entry['last_fetch'])
        except (KeyError, ValueError):
            return None

    def set_last_fetch(
        self,
        ticker: str,
        interval: str,
        timestamp: datetime,
        rows: int = 0,
    ):
        """Update last fetch timestamp for a ticker+interval.

        Args:
            ticker: Symbol.
            interval: Data interval.
            timestamp: Fetch timestamp (will be converted to UTC ISO format).
            rows: Number of rows in the CSV after fetch.
        """
        if ticker not in self._data:
            self._data[ticker] = {}

        # Normalize timestamp to UTC ISO format
        if timestamp.tzinfo is None:
            ts_str = timestamp.replace(tzinfo=timezone.utc).isoformat()
        else:
            ts_str = timestamp.astimezone(timezone.utc).isoformat()

        self._data[ticker][interval] = {
            'last_fetch': ts_str,
            'rows': rows,
        }
        self._save()

    def get_all(self) -> dict:
        """Return all metadata."""
        return dict(self._data)

    def _load(self) -> dict:
        """Load metadata from JSON file."""
        if not self.file.exists():
            return {}
        try:
            with open(self.file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load fetch metadata: {e}")
            return {}

    def _save(self):
        """Atomically save metadata to JSON file."""
        self.file.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Write to temp file, then rename (atomic on most filesystems)
            fd, tmp_path = tempfile.mkstemp(
                dir=self.file.parent,
                suffix='.tmp',
                prefix='fetch_metadata_',
            )
            try:
                with os.fdopen(fd, 'w') as f:
                    json.dump(self._data, f, indent=2)
                os.replace(tmp_path, self.file)
            except Exception:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except OSError as e:
            logger.warning(f"Failed to save fetch metadata: {e}")
