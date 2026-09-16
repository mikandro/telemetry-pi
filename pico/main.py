# MicroPython firmware for the Raspberry Pi Pico H sensor + display node.
#
# Two-way over USB serial:
#   up   -> one JSON line per interval: {"ambient_temp_c":..,"ambient_humidity_pct":..}
#   down <- display commands from the Pi: {"line1":..,"line2":..,"state":..,"mold":..}
#           which drive the 16x2 I2C LCD and the 12-LED RGB ring.
#
# Every peripheral degrades gracefully: a missing DHT20, LCD or ring just means
# that part is skipped. Flash aht20.py, lcd.py and this file (see pico/README.md).

import json
import select
import sys
import time

import neopixel
from machine import I2C, Pin

from aht20 import decode
from lcd import I2cLcd, find_lcd

# --- wiring / config ---------------------------------------------------------
I2C_ID = 1
SDA_PIN = 14           # GP14 -> DHT20 + LCD SDA (shared I2C bus)
SCL_PIN = 15           # GP15 -> DHT20 + LCD SCL
DHT20_ADDR = 0x38
RING_PIN = 2           # GP2  -> RGB ring DIN
RING_N = 12
SENSOR_INTERVAL_MS = 15000
# -----------------------------------------------------------------------------

led = Pin(25, Pin.OUT)
i2c = I2C(I2C_ID, sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=100000)
ring = neopixel.NeoPixel(Pin(RING_PIN), RING_N)

# Ring colours per advisor state (kept dim to stay within USB power budget).
STATE_COLORS = {
    "ventilate": (0, 0, 40),      # blue: open the window
    "keep_closed": (40, 14, 0),   # amber: keep it closed
    "comfortable": (0, 40, 0),    # green: all good
    "unknown": (8, 8, 8),         # dim white: no outdoor data
}
MOLD_COLOR = (60, 0, 0)           # red overlay when mold risk is flagged


def set_ring(color):
    for i in range(RING_N):
        ring[i] = color
    ring.write()


# Optional LCD.
lcd = None
try:
    _addr = find_lcd(i2c)
    if _addr is not None:
        lcd = I2cLcd(i2c, _addr, rows=2, cols=16)
        lcd.move_to(0, 0)
        lcd.putstr("Pi Telemetry")
        lcd.move_to(0, 1)
        lcd.putstr("starting...")
except OSError:
    lcd = None

set_ring((0, 0, 0))


def emit(obj):
    print(json.dumps(obj))


def lcd_line(row, text):
    if lcd is None:
        return
    text = (str(text) + " " * 16)[:16]  # pad/truncate to the display width
    try:
        lcd.move_to(0, row)
        lcd.putstr(text)
    except OSError:
        pass


def handle_command(line):
    try:
        cmd = json.loads(line)
    except ValueError:
        return
    if not isinstance(cmd, dict):
        return
    if "line1" in cmd:
        lcd_line(0, cmd["line1"])
    if "line2" in cmd:
        lcd_line(1, cmd["line2"])
    state = cmd.get("state")
    if state is not None:
        color = MOLD_COLOR if cmd.get("mold") else STATE_COLORS.get(state, (8, 8, 8))
        try:
            set_ring(color)
        except Exception:
            pass


def dht20_init():
    time.sleep_ms(40)
    try:
        status = i2c.readfrom(DHT20_ADDR, 1)[0]
    except OSError:
        return False
    if not (status & 0x08):
        i2c.writeto(DHT20_ADDR, bytes([0xBE, 0x08, 0x00]))
        time.sleep_ms(10)
    return True


def send_sensor():
    try:
        temp_c, humidity_pct, busy, crc_ok = decode(_measure())
        if busy or not crc_ok:
            emit({"error": "bad_frame"})
        else:
            emit({"ambient_temp_c": round(temp_c, 2), "ambient_humidity_pct": round(humidity_pct, 2)})
            led.toggle()
    except OSError:
        emit({"error": "i2c_read_failed"})


def _measure():
    i2c.writeto(DHT20_ADDR, bytes([0xAC, 0x33, 0x00]))
    time.sleep_ms(80)
    return i2c.readfrom(DHT20_ADDR, 7)


dht20_init()

# Poll USB serial for incoming commands without blocking the sensor cadence.
_poller = select.poll()
_poller.register(sys.stdin, select.POLLIN)

_last_sensor = time.ticks_ms()
send_sensor()  # emit one reading immediately on boot

while True:
    if _poller.poll(50):  # wait up to 50ms for a command
        line = sys.stdin.readline()
        if line:
            handle_command(line)
    now = time.ticks_ms()
    if time.ticks_diff(now, _last_sensor) >= SENSOR_INTERVAL_MS:
        _last_sensor = now
        send_sensor()
