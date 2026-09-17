"""Phase 1 collector entrypoint.

Samples system/Pi metrics on an interval and appends them to a local SQLite
database. No AWS yet: the goal here is to confirm the data looks sane.

    python -m collector.collector --once            # one sample, print it
    python -m collector.collector --interval 60     # loop, write to the db
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from contextlib import ExitStack
from types import FrameType
from typing import Optional

from .advisor import Advisor
from .cycle import AdviceStep, CollectionCycle, Sink, StdoutSink
from .metrics import Sampler
from .serial_reader import AmbientReader, PicoDisplaySink
from .storage import Storage, open_storage
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
        help="take a single sample, print it as JSON, and exit (never writes to the db)",
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
    p.add_argument(
        "--pico-display",
        action="store_true",
        help="push the ventilation advice to the Pico's LCD + RGB ring over serial "
        "(requires the display firmware; needs --advisor and --serial-port)",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return p.parse_args(argv)


def _build_cycle(
    args: argparse.Namespace,
    ambient: Optional[AmbientReader],
    sinks: list[Sink],
) -> CollectionCycle:
    """Turn CLI options plus already-started collaborators into a cycle."""
    advice = None
    if args.advisor:
        advice = AdviceStep(Advisor(), OutdoorSource(lat=args.lat, lon=args.lon))
    if args.pico_display and ambient is not None:
        sinks = [*sinks, PicoDisplaySink(ambient)]
    return CollectionCycle(Sampler(disk_path=args.disk_path, ambient_reader=ambient), advice, sinks)


def _run_once(args: argparse.Namespace, ambient: Optional[AmbientReader]) -> None:
    """Take one reading and print it. CPU% and net rates need an interval to
    measure over, so prime the sampler, wait briefly, then read."""
    cycle = _build_cycle(args, ambient, [StdoutSink()])
    # Give the sensor node a moment to push a first reading over serial.
    time.sleep(3.0 if ambient else 1.0)
    cycle.tick()


def _run_loop(args: argparse.Namespace, ambient: Optional[AmbientReader], store: Storage) -> None:
    stopper = _Stopper()
    cycle = _build_cycle(args, ambient, [store])
    log.info("writing to %s every %.0fs (%d rows so far)", args.db, args.interval, store.count())
    if ambient:
        log.info("reading ambient sensor from %s", args.serial_port)
    if cycle.advice:
        log.info("ventilation advisor enabled")
    if args.pico_display:
        log.info("pushing advice to the Pico display")
    while not stopper.stopped:
        start = time.monotonic()
        try:
            reading = cycle.tick()
            log.debug(
                "wrote sample cpu=%.1f%% ambient=%s vent=%s",
                reading.cpu_percent, reading.ambient_temp_c, reading.ventilation_state,
            )
        except Exception:  # keep the loop alive across transient failures
            log.exception("sample failed, continuing")
        # Sleep the remainder of the interval, interruptibly.
        remaining = args.interval - (time.monotonic() - start)
        while remaining > 0 and not stopper.stopped:
            nap = min(1.0, remaining)
            time.sleep(nap)
            remaining -= nap
    log.info("stopped (%d rows total)", store.count())


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    with ExitStack() as stack:
        ambient = None
        if args.serial_port:
            ambient = AmbientReader(port=args.serial_port).start()
            stack.callback(ambient.stop)
        if args.once:
            _run_once(args, ambient)
        else:
            _run_loop(args, ambient, stack.enter_context(open_storage(args.db)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
