"""The collection cycle: produce a Reading, advise on it, deliver it.

One tick is the whole repeated step the collector performs; the entrypoint only
decides when to tick and owns the lifecycle of the collaborators (serial reader,
storage). Everything here is handed in, so tests can swap any part.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from typing import TYPE_CHECKING, Optional, Sequence

from .advisor import Advisor
from .metrics import Reading
from .weather import OutdoorSource

log = logging.getLogger("collector.cycle")


if TYPE_CHECKING:
    # typing.Protocol needs Python 3.8; the Buster Pi runs 3.7, so these
    # structural types exist for type checkers only.
    from typing import Protocol

    class ReadingSource(Protocol):
        def sample(self) -> Reading: ...

    class Sink(Protocol):
        """Somewhere a Reading is recorded or shown (SQLite, Pico display, stdout)."""

        def write(self, reading: Reading) -> None: ...


class AdviceStep:
    """Fills the ventilation-advisor fields on a Reading from the indoor ambient
    values and the current outdoor conditions."""

    def __init__(self, advisor: Advisor, outdoor: OutdoorSource) -> None:
        self.advisor = advisor
        self.outdoor = outdoor

    def apply(self, reading: Reading) -> Reading:
        """Return the reading with advice added, or unchanged when there is no
        indoor reading to reason about."""
        if reading.ambient_temp_c is None or reading.ambient_humidity_pct is None:
            return reading
        advice = self.advisor.evaluate(
            reading.ambient_temp_c, reading.ambient_humidity_pct, self.outdoor.current()
        )
        return dataclasses.replace(reading, **advice.as_reading_fields())


class StdoutSink:
    """Prints each Reading as JSON (used by --once)."""

    def write(self, reading: Reading) -> None:
        print(json.dumps(reading.as_dict(), indent=2))


class CollectionCycle:
    def __init__(
        self,
        sampler: ReadingSource,
        advice: Optional[AdviceStep] = None,
        sinks: Sequence[Sink] = (),
    ) -> None:
        self.sampler = sampler
        self.advice = advice
        self.sinks = list(sinks)

    def tick(self) -> Reading:
        """Take one Reading, advise on it, and hand it to every sink in order.

        Sampling or advice failures raise. A failing sink is logged and skipped
        so the remaining sinks still receive the reading.
        """
        reading = self.sampler.sample()
        if self.advice is not None:
            reading = self.advice.apply(reading)
        for sink in self.sinks:
            try:
                sink.write(reading)
            except Exception:
                log.exception("sink %s failed, continuing", type(sink).__name__)
        return reading
