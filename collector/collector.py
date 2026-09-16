"""Phase 1 collector entrypoint.

Samples system/Pi metrics on an interval and appends them to a local SQLite
database. No AWS yet: the goal here is to confirm the data looks sane.

    python -m collector.collector --once            # one sample, print it
    python -m collector.collector --interval 60     # loop, write to the db
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import signal
import sys
import time
from types import FrameType
from typing import Optional

from .advisor import Advisor
from .metrics import Reading, Sampler
from .serial_reader import AmbientReader
from .storage import open_storage
from .weather import DEFAULT_LAT, DEFAULT_LON, OutdoorSource

log = logging.getLogger("collector")

DEFAULT_DB = "data/telemetry.sqlite"
DEFAULT_INTERVAL = 60.0


class _Stopper:
    """Flips to stopped on SIGINT/SIGTERM so the loop exits cleanly between
    samples instead of dying mid-write."""

    def __init__(self) -> None:
        self.stopped = False
        signal.signal(signal.SIGINT, self._handle)
        signal.signal(signal.SIGTERM, self._handle)

    def _handle(self, signum: int, _frame: Optional[FrameType]) -> None:
        log.info("received signal %s, stopping after current sample", signum)
        self.stopped = True


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Raspberry Pi telemetry collector")
    p.add_argument("--db", default=DEFAULT_DB, help=f"SQLite path (default: {DEFAULT_DB})")
    p.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help=f"seconds between samples (default: {DEFAULT_INTERVAL})",
    )
    p.add_argument(
        "--once",
        action="store_true",
        help="take a single sample, print it as JSON, and exit (no db write unless --db given explicitly)",
    )
    p.add_argument("--disk-path", default="/", help="filesystem to report usage for (default: /)")
    p.add_argument(
        "--serial-port",
        default=None,
        help="serial port of the Pico DHT20 sensor node, e.g. /dev/pico "
        "(omit to run without ambient temp/humidity)",
    )
    p.add_argument(
        "--advisor",
        action="store_true",
        help="enable the ventilation advisor (compares indoor vs outdoor absolute humidity)",
    )
    p.add_argument("--lat", type=float, default=DEFAULT_LAT, help="latitude for outdoor weather")
    p.add_argument("--lon", type=float, default=DEFAULT_LON, help="longitude for outdoor weather")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return p.parse_args(argv)


def _make_ambient_reader(serial_port: Optional[str]) -> Optional[AmbientReader]:
    if not serial_port:
        return None
    return AmbientReader(port=serial_port).start()


def _enrich_with_advice(
    reading: Reading,
    advisor: Optional[Advisor],
    weather: Optional[OutdoorSource],
) -> Reading:
    """Fill the ventilation-advisor fields on a reading, if enabled and there is
    an indoor reading to reason about."""
    if advisor is None or reading.ambient_temp_c is None or reading.ambient_humidity_pct is None:
        return reading
    outdoor = weather.current() if weather else None
    advice = advisor.evaluate(reading.ambient_temp_c, reading.ambient_humidity_pct, outdoor)
    return dataclasses.replace(reading, **advice.as_reading_fields())


def run_once(
    disk_path: str,
    serial_port: Optional[str] = None,
    advisor: Optional[Advisor] = None,
    weather: Optional[OutdoorSource] = None,
) -> dict:
    """Take one sample. CPU% and net rates need an interval to measure over,
    so prime the sampler, wait briefly, then read."""
    ambient = _make_ambient_reader(serial_port)
    sampler = Sampler(disk_path=disk_path, ambient_reader=ambient)
    # Give the sensor node a moment to push a first reading over serial.
    time.sleep(3.0 if ambient else 1.0)
    try:
        return _enrich_with_advice(sampler.sample(), advisor, weather).as_dict()
    finally:
        if ambient:
            ambient.stop()


def run_loop(
    db_path: str,
    interval: float,
    disk_path: str,
    serial_port: Optional[str] = None,
    advisor: Optional[Advisor] = None,
    weather: Optional[OutdoorSource] = None,
) -> None:
    stopper = _Stopper()
    ambient = _make_ambient_reader(serial_port)
    sampler = Sampler(disk_path=disk_path, ambient_reader=ambient)
    with open_storage(db_path) as store:
        log.info("writing to %s every %.0fs (%d rows so far)", db_path, interval, store.count())
        if serial_port:
            log.info("reading ambient sensor from %s", serial_port)
        if advisor:
            log.info("ventilation advisor enabled")
        while not stopper.stopped:
            start = time.monotonic()
            try:
                reading = _enrich_with_advice(sampler.sample(), advisor, weather)
                store.write(reading)
                log.debug(
                    "wrote sample cpu=%.1f%% ambient=%s vent=%s",
                    reading.cpu_percent, reading.ambient_temp_c, reading.ventilation_state,
                )
            except Exception:  # keep the loop alive across transient failures
                log.exception("sample/write failed, continuing")
            # Sleep the remainder of the interval, interruptibly.
            elapsed = time.monotonic() - start
            remaining = interval - elapsed
            while remaining > 0 and not stopper.stopped:
                nap = min(1.0, remaining)
                time.sleep(nap)
                remaining -= nap
        if ambient:
            ambient.stop()
        log.info("stopped (%d rows total)", store.count())


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    advisor = Advisor() if args.advisor else None
    weather = OutdoorSource(lat=args.lat, lon=args.lon) if args.advisor else None

    if args.once:
        print(json.dumps(run_once(args.disk_path, args.serial_port, advisor, weather), indent=2))
        return 0

    run_loop(args.db, args.interval, args.disk_path, args.serial_port, advisor, weather)
    return 0


if __name__ == "__main__":
    sys.exit(main())
