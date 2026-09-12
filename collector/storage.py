"""Local SQLite persistence for telemetry readings.

Phase 1 writes here so we can validate the data looks sane before any AWS is
involved. The column set mirrors Reading; adding a field there means adding a
column here (and a migration once there is real data to keep).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .metrics import Reading

_SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    ts                        TEXT    NOT NULL,
    cpu_percent               REAL    NOT NULL,
    load1                     REAL    NOT NULL,
    load5                     REAL    NOT NULL,
    load15                    REAL    NOT NULL,
    mem_percent               REAL    NOT NULL,
    mem_used_bytes            INTEGER NOT NULL,
    mem_total_bytes           INTEGER NOT NULL,
    swap_percent              REAL    NOT NULL,
    disk_percent              REAL    NOT NULL,
    disk_used_bytes           INTEGER NOT NULL,
    disk_total_bytes          INTEGER NOT NULL,
    net_tx_bytes              INTEGER NOT NULL,
    net_rx_bytes              INTEGER NOT NULL,
    net_tx_rate               REAL    NOT NULL,
    net_rx_rate               REAL    NOT NULL,
    uptime_s                  REAL    NOT NULL,
    cpu_temp_c                REAL,
    core_volts                REAL,
    throttled_hex             TEXT,
    under_voltage_now         INTEGER,
    under_voltage_since_boot  INTEGER,
    throttled_now             INTEGER,
    throttled_since_boot      INTEGER,
    ambient_temp_c            REAL,
    ambient_humidity_pct      REAL
);
CREATE INDEX IF NOT EXISTS idx_readings_ts ON readings (ts);
"""

# Columns that may be absent in databases created by an older schema version.
# Added via ALTER TABLE on startup so existing data keeps working.
_MIGRATION_COLUMNS = {
    "ambient_temp_c": "REAL",
    "ambient_humidity_pct": "REAL",
}


class Storage:
    """Thin wrapper around a SQLite connection for appending readings."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False keeps this usable from a scheduler thread
        # later; access stays single-threaded within the collector loop.
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        # WAL keeps writes from blocking Grafana's reads once Phase 2 lands.
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        """Add any columns missing from an older-schema database."""
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(readings)")}
        for column, decl in _MIGRATION_COLUMNS.items():
            if column not in existing:
                self._conn.execute(f"ALTER TABLE readings ADD COLUMN {column} {decl}")

    def write(self, reading: Reading) -> None:
        data = reading.as_dict()
        columns = ", ".join(data.keys())
        placeholders = ", ".join(f":{k}" for k in data.keys())
        self._conn.execute(
            f"INSERT INTO readings ({columns}) VALUES ({placeholders})", data
        )
        self._conn.commit()

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


@contextmanager
def open_storage(db_path: str | Path) -> Iterator[Storage]:
    store = Storage(db_path)
    try:
        yield store
    finally:
        store.close()
