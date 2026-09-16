"""Pi-side reader for the Pico DHT20 sensor node.

Runs a background thread that reads newline-delimited JSON from the Pico over
USB serial, keeping the most recent ambient reading. It degrades gracefully:
if pyserial is missing, the port is absent/unplugged, or readings go stale, the
collector simply records NULL ambient values (same pattern as vcgencmd metrics),
so the system runs fine with or without the sensor node attached.

Wire format from the Pico (one JSON object per line):
    {"ambient_temp_c": 21.5, "ambient_humidity_pct": 47.2}
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Optional, Tuple

try:
    import serial  # pyserial
except ImportError:  # keep the collector importable without pyserial installed
    serial = None  # type: ignore

log = logging.getLogger("collector.serial")

# The Pico enumerates as this USB vendor/product when running MicroPython;
# deploy/udev/99-pico.rules maps it to a stable /dev/pico symlink.
DEFAULT_PORT = "/dev/pico"
DEFAULT_BAUD = 115200


class AmbientReader:
    """Background serial reader holding the latest ambient reading."""

    def __init__(
        self,
        port: str = DEFAULT_PORT,
        baud: int = DEFAULT_BAUD,
        stale_after_s: float = 90.0,
        reconnect_delay_s: float = 5.0,
    ) -> None:
        self.port = port
        self.baud = baud
        self.stale_after_s = stale_after_s
        self.reconnect_delay_s = reconnect_delay_s
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._latest: Optional[Tuple[float, float, float]] = None  # (mono, temp, hum)
        self._serial = None  # set while connected, for sending display commands
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "AmbientReader":
        if serial is None:
            log.warning("pyserial not installed; ambient readings disabled")
            return self
        self._thread = threading.Thread(
            target=self._run, name="ambient-reader", daemon=True
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def read(self) -> Tuple[Optional[float], Optional[float]]:
        """Return (temp_c, humidity_pct), or (None, None) if absent/stale."""
        with self._lock:
            latest = self._latest
        if latest is None:
            return (None, None)
        mono, temp, hum = latest
        if time.monotonic() - mono > self.stale_after_s:
            return (None, None)
        return (temp, hum)

    def send(self, obj: dict) -> bool:
        """Send a display command (JSON line) to the Pico. No-op if not
        connected or pyserial is missing. Returns True if written."""
        with self._lock:
            ser = self._serial
        if ser is None:
            return False
        try:
            with self._write_lock:
                ser.write((json.dumps(obj) + "\n").encode("utf-8"))
            return True
        except (OSError, ValueError):
            return False

    def ingest(self, line: bytes) -> bool:
        """Parse one raw line; update latest on success. Returns True if used.

        Separate from the I/O loop so it can be unit-tested without a port.
        """
        try:
            obj = json.loads(line.decode("utf-8").strip())
            temp = float(obj["ambient_temp_c"])
            hum = float(obj["ambient_humidity_pct"])
        except (ValueError, KeyError, AttributeError, UnicodeDecodeError):
            return False  # blank line, error frame, or malformed JSON
        with self._lock:
            self._latest = (time.monotonic(), temp, hum)
        return True

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                with serial.Serial(self.port, self.baud, timeout=2) as ser:
                    with self._lock:
                        self._serial = ser
                    log.info("ambient reader connected to %s", self.port)
                    while not self._stop.is_set():
                        line = ser.readline()
                        if line:
                            self.ingest(line)
            except (OSError, serial.SerialException) as exc:  # type: ignore[attr-defined]
                # Port missing or unplugged: wait, then retry (the Pico may not
                # be attached yet, or may have reset).
                log.debug("serial unavailable (%s); retrying in %ss", exc, self.reconnect_delay_s)
                self._stop.wait(self.reconnect_delay_s)
            finally:
                with self._lock:
                    self._serial = None
