# Pi Telemetry

A Raspberry Pi that records its own health and the room's climate, and advises when to open the window.

## Language

**Reading**:
One point-in-time record of Pi health, indoor ambient conditions and, when enabled, ventilation advice.
_Avoid_: sample, row, metric (for the whole record)

**Collection cycle**:
The single repeated step of producing a Reading, adding ventilation advice to it, and delivering it to wherever it is recorded or shown.
_Avoid_: collector (names the package and the process), loop (the schedule, not the step)
