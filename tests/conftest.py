"""Shared test helpers."""

from collector.metrics import Reading


def make_reading(**over) -> Reading:
    """A fixed Reading built without touching psutil or vcgencmd."""
    fields = dict(
        ts="2026-09-17T12:00:00+00:00",
        cpu_percent=12.5,
        load1=0.1, load5=0.2, load15=0.3,
        mem_percent=40.0, mem_used_bytes=400, mem_total_bytes=1000,
        swap_percent=0.0,
        disk_percent=50.0, disk_used_bytes=500, disk_total_bytes=1000,
        net_tx_bytes=10, net_rx_bytes=20, net_tx_rate=1.0, net_rx_rate=2.0,
        uptime_s=3600.0,
        cpu_temp_c=None, core_volts=None, throttled_hex=None,
        under_voltage_now=None, under_voltage_since_boot=None,
        throttled_now=None, throttled_since_boot=None,
        ambient_temp_c=21.0, ambient_humidity_pct=65.0,
    )
    fields.update(over)
    return Reading(**fields)
