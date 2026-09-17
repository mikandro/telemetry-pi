"""Tests for the Pico display-command builder and serial send."""

import json
import os
import time

import pytest

from collector.serial_reader import AmbientReader, PicoDisplaySink, display_command
from tests.conftest import make_reading as _reading


def test_display_command_ventilate_with_outdoor():
    cmd = display_command(_reading(
        ambient_temp_c=21.4, ambient_humidity_pct=60.0,
        outdoor_temp_c=5.2, outdoor_humidity_pct=80.0,
        ventilation_state="ventilate", mold_risk=1,
    ))
    assert cmd["line1"] == "In21C60 Out5C80"
    assert cmd["line2"] == "!OPEN WINDOW"   # "!" prefix flags mold risk
    assert cmd["state"] == "ventilate"
    assert cmd["mold"] == 1
    assert len(cmd["line1"]) <= 16 and len(cmd["line2"]) <= 16


def test_display_command_unknown_without_outdoor():
    cmd = display_command(_reading(
        ambient_temp_c=21.0, ambient_humidity_pct=48.0,
        outdoor_temp_c=None, outdoor_humidity_pct=None,
        ventilation_state="unknown", mold_risk=0,
    ))
    assert cmd["line1"] == "In 21C 48%RH"
    assert cmd["line2"] == "NO OUTDOOR DATA"
    assert cmd["mold"] == 0


def test_display_command_none_when_no_advice():
    assert display_command(_reading(ventilation_state=None)) is None


class _RecordingReader:
    def __init__(self):
        self.sent = []

    def send(self, obj):
        self.sent.append(obj)
        return True


def test_display_sink_sends_advice_and_skips_readings_without_it():
    reader = _RecordingReader()
    sink = PicoDisplaySink(reader)
    sink.write(_reading(ventilation_state=None))
    sink.write(_reading(ventilation_state="keep_closed", mold_risk=0))
    assert [c["line2"] for c in reader.sent] == ["KEEP CLOSED"]


def test_send_returns_false_when_not_connected():
    assert AmbientReader().send({"line1": "hi"}) is False


@pytest.mark.skipif(not hasattr(os, "openpty"), reason="needs a POSIX pty")
def test_send_writes_json_line_over_pty():
    pytest.importorskip("serial")
    controller, peripheral = os.openpty()
    reader = AmbientReader(port=os.ttyname(peripheral), reconnect_delay_s=0.2).start()
    try:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not reader.send({"line1": "OPEN WINDOW", "state": "ventilate"}):
            time.sleep(0.05)
        # Read what the Pico would receive on its stdin.
        os.set_blocking(controller, False)
        time.sleep(0.2)
        received = os.read(controller, 200).decode()
        obj = json.loads(received.strip().splitlines()[-1])
        assert obj["line1"] == "OPEN WINDOW"
        assert obj["state"] == "ventilate"
    finally:
        reader.stop()
        os.close(controller)
        os.close(peripheral)
