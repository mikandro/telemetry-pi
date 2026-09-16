# Minimal HD44780 character-LCD driver over a PCF8574 I2C backpack.
#
# Self-contained MicroPython (no external libraries). Covers what the ventilation
# advisor needs: init, clear, move_to(col, row), putstr(text). Standard backpack
# bit wiring (P0=RS, P1=RW, P2=EN, P3=backlight, P4..P7=D4..D7).

import time

_RS = 0x01
_EN = 0x04
_BACKLIGHT = 0x08

_CMD_CLEAR = 0x01
_CMD_HOME = 0x02
_CMD_ENTRY = 0x06      # increment cursor, no display shift
_CMD_DISPLAY_ON = 0x0C  # display on, cursor off, blink off
_CMD_FUNCTION = 0x28    # 4-bit, 2 lines, 5x8 font
_CMD_SET_DDRAM = 0x80


def find_lcd(i2c):
    """Return the LCD's I2C address (0x27 or 0x3F) if present, else None."""
    present = i2c.scan()
    for addr in (0x27, 0x3F):
        if addr in present:
            return addr
    return None


class I2cLcd:
    def __init__(self, i2c, addr=0x27, rows=2, cols=16):
        self.i2c = i2c
        self.addr = addr
        self.rows = rows
        self.cols = cols
        self.backlight = _BACKLIGHT
        time.sleep_ms(50)
        # Wake up and switch to 4-bit mode (HD44780 init dance).
        self._strobe(0x30)
        time.sleep_ms(5)
        self._strobe(0x30)
        time.sleep_ms(1)
        self._strobe(0x30)
        time.sleep_ms(1)
        self._strobe(0x20)
        self._command(_CMD_FUNCTION)
        self._command(_CMD_DISPLAY_ON)
        self._command(_CMD_ENTRY)
        self.clear()

    def _strobe(self, data):
        # Pulse EN high then low while holding the data byte.
        self.i2c.writeto(self.addr, bytes([data | _EN | self.backlight]))
        time.sleep_us(1)
        self.i2c.writeto(self.addr, bytes([(data & ~_EN) | self.backlight]))
        time.sleep_us(50)

    def _send(self, value, rs):
        high = (value & 0xF0) | rs | self.backlight
        low = ((value << 4) & 0xF0) | rs | self.backlight
        self._strobe(high)
        self._strobe(low)

    def _command(self, value):
        self._send(value, 0)
        if value in (_CMD_CLEAR, _CMD_HOME):
            time.sleep_ms(2)

    def clear(self):
        self._command(_CMD_CLEAR)

    def move_to(self, col, row):
        offsets = (0x00, 0x40, 0x14, 0x54)
        self._command(_CMD_SET_DDRAM | (col + offsets[row]))

    def putstr(self, text):
        for ch in text:
            self._send(ord(ch), _RS)
