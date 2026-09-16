"""System and Raspberry Pi metric collection.

Cross-platform metrics come from psutil. Pi-specific metrics (SoC temperature,
core voltage, throttling/under-voltage) come from `vcgencmd` and degrade to None
on hosts where it is not available, so the collector can be developed and tested
off-device.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

import psutil

# Bit positions in the vcgencmd `get_throttled` bitmask.
# See https://www.raspberrypi.com/documentation/computers/os.html#get_throttled
_THROTTLE_UNDER_VOLTAGE_NOW = 0x1
_THROTTLE_THROTTLED_NOW = 0x4
_THROTTLE_UNDER_VOLTAGE_SINCE_BOOT = 0x10000
_THROTTLE_THROTTLED_SINCE_BOOT = 0x40000


@dataclass
class Reading:
    """A single point-in-time telemetry sample.

    Field names double as the SQLite column names and, later, the DynamoDB
    attribute names, so keep them stable and storage-friendly.
    """

    ts: str  # ISO 8601, UTC

    cpu_percent: float
    load1: float
    load5: float
    load15: float

    mem_percent: float
    mem_used_bytes: int
    mem_total_bytes: int
    swap_percent: float

    disk_percent: float
    disk_used_bytes: int
    disk_total_bytes: int

    net_tx_bytes: int  # cumulative since boot
    net_rx_bytes: int  # cumulative since boot
    net_tx_rate: float  # bytes/sec over the sample interval
    net_rx_rate: float  # bytes/sec over the sample interval

    uptime_s: float

    # Pi-specific, None when vcgencmd is unavailable.
    cpu_temp_c: Optional[float]
    core_volts: Optional[float]
    throttled_hex: Optional[str]
    under_voltage_now: Optional[int]
    under_voltage_since_boot: Optional[int]
    throttled_now: Optional[int]
    throttled_since_boot: Optional[int]

    # External DHT20 sensor node (via the Pico over serial). None when no
    # sensor node is attached or its readings have gone stale.
    ambient_temp_c: Optional[float]
    ambient_humidity_pct: Optional[float]

    # Ventilation advisor (populated by the collector loop when --advisor is on
    # and an indoor reading is present). See collector/advisor.py.
    outdoor_temp_c: Optional[float] = None
    outdoor_humidity_pct: Optional[float] = None
    indoor_abs_humidity_gm3: Optional[float] = None
    outdoor_abs_humidity_gm3: Optional[float] = None
    dew_point_c: Optional[float] = None
    ventilation_state: Optional[str] = None
    should_ventilate: Optional[int] = None
    mold_risk: Optional[int] = None

    def as_dict(self) -> dict:
        return asdict(self)


def _run_vcgencmd(*args: str) -> Optional[str]:
    """Return trimmed vcgencmd output, or None if it is unavailable/fails."""
    if shutil.which("vcgencmd") is None:
        return None
    try:
        out = subprocess.run(
            ["vcgencmd", *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    return out.stdout.strip()


def _cpu_temp_c() -> Optional[float]:
    raw = _run_vcgencmd("measure_temp")  # e.g. "temp=48.3'C"
    if not raw or "=" not in raw:
        return None
    try:
        return float(raw.split("=", 1)[1].split("'", 1)[0])
    except (ValueError, IndexError):
        return None


def _core_volts() -> Optional[float]:
    raw = _run_vcgencmd("measure_volts", "core")  # e.g. "volt=0.8563V"
    if not raw or "=" not in raw:
        return None
    try:
        return float(raw.split("=", 1)[1].rstrip("V"))
    except ValueError:
        return None


def _throttled() -> dict:
    """Decode `vcgencmd get_throttled` into a hex string plus flag ints."""
    raw = _run_vcgencmd("get_throttled")  # e.g. "throttled=0x50000"
    blank = {
        "throttled_hex": None,
        "under_voltage_now": None,
        "under_voltage_since_boot": None,
        "throttled_now": None,
        "throttled_since_boot": None,
    }
    if not raw or "=" not in raw:
        return blank
    try:
        value = int(raw.split("=", 1)[1], 16)
    except ValueError:
        return blank
    return {
        "throttled_hex": hex(value),
        "under_voltage_now": int(bool(value & _THROTTLE_UNDER_VOLTAGE_NOW)),
        "under_voltage_since_boot": int(bool(value & _THROTTLE_UNDER_VOLTAGE_SINCE_BOOT)),
        "throttled_now": int(bool(value & _THROTTLE_THROTTLED_NOW)),
        "throttled_since_boot": int(bool(value & _THROTTLE_THROTTLED_SINCE_BOOT)),
    }


class Sampler:
    """Produces Readings, tracking prior counters so CPU% and network rates
    are measured over the interval between samples rather than since boot."""

    def __init__(self, disk_path: str = "/", ambient_reader=None) -> None:
        self.disk_path = disk_path
        # Optional object with a .read() -> (temp_c, humidity_pct) method
        # (collector.serial_reader.AmbientReader). Duck-typed to avoid coupling.
        self.ambient_reader = ambient_reader
        # Prime psutil's internal CPU counters so the first real sample is
        # measured against this call rather than against process start.
        psutil.cpu_percent(interval=None)
        self._prev_net = psutil.net_io_counters()
        self._prev_monotonic = time.monotonic()

    def sample(self) -> Reading:
        now_mono = time.monotonic()
        elapsed = now_mono - self._prev_monotonic
        if elapsed <= 0:
            elapsed = 1e-9

        net = psutil.net_io_counters()
        tx_rate = (net.bytes_sent - self._prev_net.bytes_sent) / elapsed
        rx_rate = (net.bytes_recv - self._prev_net.bytes_recv) / elapsed
        self._prev_net = net
        self._prev_monotonic = now_mono

        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage(self.disk_path)
        load1, load5, load15 = os.getloadavg()

        if self.ambient_reader is not None:
            ambient_temp_c, ambient_humidity_pct = self.ambient_reader.read()
        else:
            ambient_temp_c, ambient_humidity_pct = None, None

        return Reading(
            ts=datetime.now(timezone.utc).isoformat(),
            cpu_percent=psutil.cpu_percent(interval=None),
            load1=load1,
            load5=load5,
            load15=load15,
            mem_percent=mem.percent,
            mem_used_bytes=mem.used,
            mem_total_bytes=mem.total,
            swap_percent=swap.percent,
            disk_percent=disk.percent,
            disk_used_bytes=disk.used,
            disk_total_bytes=disk.total,
            net_tx_bytes=net.bytes_sent,
            net_rx_bytes=net.bytes_recv,
            net_tx_rate=tx_rate,
            net_rx_rate=rx_rate,
            uptime_s=time.time() - psutil.boot_time(),
            cpu_temp_c=_cpu_temp_c(),
            core_volts=_core_volts(),
            **_throttled(),
            ambient_temp_c=ambient_temp_c,
            ambient_humidity_pct=ambient_humidity_pct,
        )
