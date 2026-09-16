# Pico sensor + display node

The Raspberry Pi Pico H reads the DHT20 temperature/humidity sensor and streams
readings to the Pi 4 over USB serial, and (optionally) drives a 16x2 I2C LCD and
a 12-LED RGB ring from display commands the Pi sends back. See
[`collector/serial_reader.py`](../collector/serial_reader.py) and
[`docs/ventilation-advisor.md`](../docs/ventilation-advisor.md).

The Pico H has no clock or network, so it sends only measurements; the Pi
timestamps them and computes the ventilation advice.

## Files (flash all that apply)
- `aht20.py` — pure AHT20 frame decode (shared with the unit tests).
- `lcd.py` — minimal HD44780-over-PCF8574 I2C LCD driver.
- `main.py` — firmware: stream the sensor up, drive the LCD + ring from commands.

## Wiring
The DHT20 and the LCD share one I2C bus (I2C1 on GP14/GP15), so the LCD adds no
new pins. The RGB ring uses one GPIO for data. Change the pins at the top of
`main.py` if you wire it differently.

**DHT20** (waffle/holes face toward you; legs left to right are VDD, SDA, GND, SCL):

| DHT20 leg | Pico pin |
|-----------|----------|
| VDD | 3V3 OUT (phys. 36) |
| SDA | GP14 (phys. 19) |
| GND | GND (phys. 18) |
| SCL | GP15 (phys. 20) |

**16x2 LCD (I2C backpack)** — tap onto the same I2C bus:

| LCD pin | Pico pin |
|---------|----------|
| VCC | VBUS 5V (phys. 40) *or* 3V3 OUT |
| GND | GND |
| SDA | GP14 (shared with the DHT20) |
| SCL | GP15 (shared with the DHT20) |

**12-LED RGB ring**:

| Ring pin | Pico pin |
|----------|----------|
| VCC / 5V | VBUS 5V (phys. 40) |
| GND | GND |
| DIN | GP2 (phys. 4) |

Ring brightness is capped in firmware to stay within the USB power budget; don't
raise it much if the ring is powered from the Pico.

## Flashing
1. Install MicroPython: hold BOOTSEL, plug in USB, drop the MicroPython `.uf2`
   onto the `RPI-RP2` drive.
2. Copy `aht20.py`, `lcd.py` and `main.py` to the Pico
   (`mpremote cp aht20.py lcd.py main.py :`, or Thonny "Save to Pico").
3. `main.py` runs automatically on boot/reset.

## Enabling the display
On the Pi, run the collector with `--pico-display` (needs `--advisor` and
`--serial-port`), or set `PICO_DISPLAY=1` for the Buster runner. The LCD then
shows the indoor/outdoor readings and the verdict, and the ring shows the state.

## Protocol (newline-delimited JSON, both ways)
- **Up** (Pico -> Pi): `{"ambient_temp_c": <float>, "ambient_humidity_pct": <float>}`,
  or `{"error": "dht20_not_found" | "bad_frame" | "i2c_read_failed"}`.
- **Down** (Pi -> Pico): `{"line1": <str>, "line2": <str>, "state": "ventilate" |
  "keep_closed" | "comfortable" | "unknown", "mold": 0 | 1}`. `line1`/`line2` go
  to the LCD; `state` sets the ring colour (mold risk overrides to red).

## Verifying the stream
```bash
cat /dev/ttyACM0        # or: mpremote  (Ctrl-] to exit)
```
Every peripheral degrades gracefully: a missing DHT20, LCD or ring just skips
that part.
