"""Tests for the Pi-side ambient serial reader."""

import os
import time

import pytest

from collector.serial_reader import AmbientReader


def test_ingest_valid_line_updates_latest():
    r = AmbientReader()
    assert r.ingest(b'{"ambient_temp_c": 21.5, "ambient_humidity_pct": 47.2}\n')
    temp, hum = r.read()
    assert temp == 21.5
    assert hum == 47.2


def test_ingest_ignores_malformed_and_error_frames():
    r = AmbientReader()
    assert not r.ingest(b"not json\n")
    assert not r.ingest(b'{"error": "dht20_not_found"}\n')
    assert not r.ingest(b"\n")
    assert r.read() == (None, None)


def test_reading_goes_stale():
    r = AmbientReader(stale_after_s=0.05)
    r.ingest(b'{"ambient_temp_c": 20.0, "ambient_humidity_pct": 40.0}')
    assert r.read() == (20.0, 40.0)
    time.sleep(0.08)
    assert r.read() == (None, None)  # too old now


def test_no_data_reads_none():
    assert AmbientReader().read() == (None, None)


@pytest.mark.skipif(not hasattr(os, "openpty"), reason="needs a POSIX pty")
def test_end_to_end_over_pty():
    """Drive the full background reader through a real serial device (a pty),
    standing in for the Pico, and confirm readings land."""
    serial = pytest.importorskip("serial")
    controller, peripheral = os.openpty()
    port_name = os.ttyname(peripheral)

    reader = AmbientReader(port=port_name, reconnect_delay_s=0.2).start()
    try:
        # Re-send each iteration: the Pico streams continuously, and this also
        # avoids racing the reader thread's initial port open.
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            os.write(controller, b'{"ambient_temp_c": 18.75, "ambient_humidity_pct": 55.5}\n')
            if reader.read() != (None, None):
                break
            time.sleep(0.1)
        assert reader.read() == (18.75, 55.5)
    finally:
        reader.stop()
        os.close(controller)
        os.close(peripheral)
