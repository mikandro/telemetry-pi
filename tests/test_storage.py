"""Tests for SQLite persistence."""

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
