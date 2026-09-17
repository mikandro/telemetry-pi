"""Tests for the collection cycle: sample, advise, deliver."""

import sqlite3

from collector.advisor import VENTILATE, Advisor
from collector.cycle import AdviceStep, CollectionCycle
from collector.storage import Storage
from collector.weather import OutdoorSource
from tests.conftest import make_reading


class FakeSampler:
    def __init__(self, reading):
        self.reading = reading

    def sample(self):
        return self.reading


class RecordingSink:
    def __init__(self):
        self.readings = []

    def write(self, reading):
        self.readings.append(reading)


class FailingSink:
    def write(self, reading):
        raise OSError("serial unplugged")


def _advice(outdoor=(5.0, 80.0)):
    return AdviceStep(Advisor(), OutdoorSource(fetch_fn=lambda lat, lon: outdoor))


def test_tick_fills_advice_and_delivers():
    sink = RecordingSink()
    cycle = CollectionCycle(FakeSampler(make_reading()), advice=_advice(), sinks=[sink])

    reading = cycle.tick()

    assert reading.ventilation_state == VENTILATE
    assert reading.outdoor_temp_c == 5.0
    assert reading.mold_risk == 1
    assert sink.readings == [reading]


def test_tick_skips_advice_without_ambient_reading():
    sink = RecordingSink()
    base = make_reading(ambient_temp_c=None, ambient_humidity_pct=None)
    cycle = CollectionCycle(FakeSampler(base), advice=_advice(), sinks=[sink])

    reading = cycle.tick()

    assert reading.ventilation_state is None
    assert reading.outdoor_temp_c is None
    assert sink.readings == [reading]


def test_tick_without_advice_passes_reading_through():
    base = make_reading()
    cycle = CollectionCycle(FakeSampler(base))

    assert cycle.tick() == base


def test_failing_sink_does_not_block_later_sinks():
    sink = RecordingSink()
    cycle = CollectionCycle(FakeSampler(make_reading()), sinks=[FailingSink(), sink])

    reading = cycle.tick()

    assert sink.readings == [reading]


def test_storage_sink_persists_one_row_per_tick(tmp_path):
    db = tmp_path / "t.sqlite"
    with Storage(db) as store:
        cycle = CollectionCycle(FakeSampler(make_reading()), advice=_advice(), sinks=[store])
        cycle.tick()
        assert store.count() == 1
    row = sqlite3.connect(db).execute("SELECT ventilation_state FROM readings").fetchone()
    assert row == (VENTILATE,)
