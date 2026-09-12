# MicroPython firmware for the Raspberry Pi Pico H acting as a DHT20 sensor node.
#
# Reads the DHT20 (AHT20-compatible) over I2C and prints one newline-delimited
# JSON reading per interval to USB serial (stdout). The Pi 4 reads that stream
# (see collector/serial_reader.py). The Pico carries no clock/network, so it
# sends only the measurements; the Pi timestamps them on receipt.
#
# Flash: copy this file and aht20.py to the Pico (see pico/README.md).

import json
import time

from machine import I2C, Pin

from aht20 import decode

# --- wiring / config (change these to match how you wired the sensor) --------
I2C_ID = 0
SDA_PIN = 0        # GP0  -> DHT20 SDA
SCL_PIN = 1        # GP1  -> DHT20 SCL
DHT20_ADDR = 0x38
INTERVAL_S = 15
# -----------------------------------------------------------------------------

led = Pin(25, Pin.OUT)  # onboard LED (GP25 on the Pico H)
i2c = I2C(I2C_ID, sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=100000)


def emit(obj):
    # print() is wired to USB serial; one compact JSON object per line.
    print(json.dumps(obj))


def init_sensor():
    time.sleep_ms(40)
    try:
        status = i2c.readfrom(DHT20_ADDR, 1)[0]
    except OSError:
        return False
    # Bit 0x08 = calibrated. If clear, send the init/calibrate command.
    if not (status & 0x08):
        i2c.writeto(DHT20_ADDR, bytes([0xBE, 0x08, 0x00]))
        time.sleep_ms(10)
    return True


def measure():
    i2c.writeto(DHT20_ADDR, bytes([0xAC, 0x33, 0x00]))  # trigger measurement
    time.sleep_ms(80)
    return decode(i2c.readfrom(DHT20_ADDR, 7))


if not init_sensor():
    emit({"error": "dht20_not_found"})

while True:
    try:
        temp_c, humidity_pct, busy, crc_ok = measure()
        if busy or not crc_ok:
            emit({"error": "bad_frame", "busy": busy, "crc_ok": crc_ok})
        else:
            emit({
                "ambient_temp_c": round(temp_c, 2),
                "ambient_humidity_pct": round(humidity_pct, 2),
            })
            led.toggle()  # heartbeat: LED flips on each good reading
    except OSError:
        emit({"error": "i2c_read_failed"})
    time.sleep(INTERVAL_S)
