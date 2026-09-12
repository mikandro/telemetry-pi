"""Tests for metric collection and vcgencmd parsing."""

import collector.metrics as metrics
from collector.metrics import Reading, Sampler


def test_sampler_produces_complete_reading():
    sampler = Sampler()
    reading = sampler.sample()

    assert isinstance(reading, Reading)
    assert 0.0 <= reading.cpu_percent <= 100.0
    assert 0.0 <= reading.mem_percent <= 100.0
    assert reading.mem_total_bytes > 0
    assert reading.disk_total_bytes > 0
    assert reading.net_tx_bytes >= 0
    assert reading.net_rx_bytes >= 0
    assert reading.uptime_s > 0
    # ts is ISO 8601 with timezone.
    assert reading.ts.endswith("+00:00")


def test_net_rates_are_non_negative():
    # Cumulative counters only grow, so rates over an interval are >= 0.
    sampler = Sampler()
    r1 = sampler.sample()
    r2 = sampler.sample()
    assert r2.net_tx_bytes >= r1.net_tx_bytes
    assert r2.net_rx_rate >= 0.0
    assert r2.net_tx_rate >= 0.0


def test_throttled_decoding_off_device(monkeypatch):
    # No vcgencmd -> all Pi-specific throttle fields are None.
    monkeypatch.setattr(metrics, "_run_vcgencmd", lambda *a: None)
    result = metrics._throttled()
    assert result["throttled_hex"] is None
    assert result["under_voltage_now"] is None


def test_throttled_decoding_under_voltage(monkeypatch):
    # 0x50005: under-voltage now + throttled now + both since-boot bits.
    monkeypatch.setattr(metrics, "_run_vcgencmd", lambda *a: "throttled=0x50005")
    result = metrics._throttled()
    assert result["throttled_hex"] == "0x50005"
    assert result["under_voltage_now"] == 1
    assert result["throttled_now"] == 1
    assert result["under_voltage_since_boot"] == 1
    assert result["throttled_since_boot"] == 1


def test_throttled_decoding_healthy(monkeypatch):
    monkeypatch.setattr(metrics, "_run_vcgencmd", lambda *a: "throttled=0x0")
    result = metrics._throttled()
    assert result["under_voltage_now"] == 0
    assert result["throttled_now"] == 0


def test_cpu_temp_parsing(monkeypatch):
    monkeypatch.setattr(metrics, "_run_vcgencmd", lambda *a: "temp=48.3'C")
    assert metrics._cpu_temp_c() == 48.3


def test_core_volts_parsing(monkeypatch):
    monkeypatch.setattr(metrics, "_run_vcgencmd", lambda *a: "volt=0.8563V")
    assert metrics._core_volts() == 0.8563
