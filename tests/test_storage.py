"""Tests for SQLite persistence."""

import sqlite3

from collector.metrics import Sampler
from collector.storage import Storage, open_storage


def test_write_and_count(tmp_path):
    db = tmp_path / "t.sqlite"
    sampler = Sampler()
    with open_storage(db) as store:
        assert store.count() == 0
        store.write(sampler.sample())
        store.write(sampler.sample())
        assert store.count() == 2
    assert db.exists()


def test_reopen_persists_rows(tmp_path):
    db = tmp_path / "t.sqlite"
    with open_storage(db) as store:
        store.write(Sampler().sample())
    # Reopen: the row survived the connection close.
    with open_storage(db) as store:
        assert store.count() == 1


def test_creates_parent_directory(tmp_path):
    db = tmp_path / "nested" / "dir" / "t.sqlite"
    store = Storage(db)
    try:
        assert db.parent.is_dir()
    finally:
        store.close()


def test_migration_adds_ambient_columns(tmp_path):
    # Simulate an older-schema database that predates the ambient columns.
    db = tmp_path / "old.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE readings (ts TEXT NOT NULL, cpu_percent REAL NOT NULL, "
        "load1 REAL, load5 REAL, load15 REAL, mem_percent REAL, mem_used_bytes INTEGER, "
        "mem_total_bytes INTEGER, swap_percent REAL, disk_percent REAL, disk_used_bytes INTEGER, "
        "disk_total_bytes INTEGER, net_tx_bytes INTEGER, net_rx_bytes INTEGER, net_tx_rate REAL, "
        "net_rx_rate REAL, uptime_s REAL, cpu_temp_c REAL, core_volts REAL, throttled_hex TEXT, "
        "under_voltage_now INTEGER, under_voltage_since_boot INTEGER, throttled_now INTEGER, "
        "throttled_since_boot INTEGER)"
    )
    conn.commit()
    conn.close()

    # Opening it should add the missing columns and accept a full Reading.
    with open_storage(db) as store:
        cols = {r[1] for r in store._conn.execute("PRAGMA table_info(readings)")}
        assert "ambient_temp_c" in cols
        assert "ambient_humidity_pct" in cols
        store.write(Sampler().sample())
        assert store.count() == 1


def test_stored_values_round_trip(tmp_path):
    db = tmp_path / "t.sqlite"
    reading = Sampler().sample()
    with open_storage(db) as store:
        store.write(reading)
        row = store._conn.execute(
            "SELECT cpu_percent, mem_total_bytes, ts FROM readings"
        ).fetchone()
    assert row[0] == reading.cpu_percent
    assert row[1] == reading.mem_total_bytes
    assert row[2] == reading.ts
