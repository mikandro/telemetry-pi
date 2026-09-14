# Pico DHT20 sensor node

The Raspberry Pi Pico H reads the DHT20 (AHT20-compatible) temperature/humidity
sensor over I2C and streams readings to the Pi 4 over USB serial. The Pi 4 folds
them into the collector (see [`collector/serial_reader.py`](../collector/serial_reader.py)).

Because the Pico H has no clock or network, it sends only measurements; the Pi 4
timestamps them on receipt.

## Files
- `aht20.py` — pure-Python AHT20 frame decode (shared with the unit tests).
- `main.py` — MicroPython firmware: read the sensor, print one JSON line per reading.

## Wiring (DHT20 to Pico)
Defaults in `main.py` use I2C1 on GP14/GP15, matching the Pi Hut "Let it Glow"
Day 9 guide. Change `SDA_PIN`/`SCL_PIN` if you wire it differently. Hold the
DHT20 with the waffle/holes face toward you; legs left to right are VDD, SDA,
GND, SCL.

| DHT20 leg (waffle facing you) | Pico pin           |
|-------------------------------|--------------------|
| Leg 1 (left) VDD              | 3V3 OUT (phys. 36) |
| Leg 2 SDA                     | GP14 (phys. 19)    |
| Leg 3 GND                     | GND (phys. 18)     |
| Leg 4 SCL                     | GP15 (phys. 20)    |

## Flashing
1. Install MicroPython on the Pico: hold BOOTSEL, plug in USB, drop the
   MicroPython `.uf2` onto the `RPI-RP2` drive.
2. Copy both `aht20.py` and `main.py` to the Pico's filesystem (Thonny: "Save
   to Raspberry Pi Pico", or `mpremote cp aht20.py main.py :`).
3. `main.py` runs automatically on boot/reset.

## Verifying the stream
Plug the Pico into the Pi 4 and watch the raw serial output:

```bash
mpremote                       # opens the REPL / stream, Ctrl-] to exit
# or:  cat /dev/pico
```

You should see lines like:

```json
{"ambient_temp_c": 21.5, "ambient_humidity_pct": 47.2}
```

## Wire format
One compact JSON object per line. Readings:
`{"ambient_temp_c": <float>, "ambient_humidity_pct": <float>}`.
Errors: `{"error": "dht20_not_found" | "bad_frame" | "i2c_read_failed", ...}`
(the Pi-side reader ignores non-reading lines).
