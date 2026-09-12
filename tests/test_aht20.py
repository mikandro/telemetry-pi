"""Tests for the AHT20/DHT20 frame decode (shared with the Pico firmware)."""

import importlib.util
import pathlib

# pico/aht20.py lives outside the collector package (it is also flashed to the
# Pico), so load it by path.
_AHT20 = pathlib.Path(__file__).resolve().parent.parent / "pico" / "aht20.py"
_spec = importlib.util.spec_from_file_location("aht20", _AHT20)
aht20 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(aht20)


def _frame(hum_raw, temp_raw, status=0x1C):
    """Build a valid 7-byte AHT20 frame (with correct CRC) from raw counts."""
    b = [
        status,
        (hum_raw >> 12) & 0xFF,
        (hum_raw >> 4) & 0xFF,
        ((hum_raw & 0x0F) << 4) | ((temp_raw >> 16) & 0x0F),
        (temp_raw >> 8) & 0xFF,
        temp_raw & 0xFF,
    ]
    b.append(aht20.crc8(b))
    return bytes(b)


def test_decode_known_values():
    # 50% RH and 25 C map to these raw 20-bit counts.
    frame = _frame(hum_raw=0x80000, temp_raw=0x60000)
    temp_c, humidity_pct, busy, crc_ok = aht20.decode(frame)
    assert round(humidity_pct, 3) == 50.0
    assert round(temp_c, 3) == 25.0
    assert busy is False
    assert crc_ok is True


def test_decode_zero_and_full_scale():
    t0, h0, _, _ = aht20.decode(_frame(0, 0))
    assert round(h0, 2) == 0.0
    assert round(t0, 2) == -50.0  # temp formula floor
    tf, hf, _, _ = aht20.decode(_frame(0xFFFFF, 0xFFFFF))
    assert round(hf, 1) == 100.0
    assert round(tf, 1) == 150.0  # temp formula ceiling


def test_busy_bit_detected():
    frame = _frame(0x80000, 0x60000, status=0x80)  # busy bit set
    _, _, busy, _ = aht20.decode(frame)
    assert busy is True


def test_bad_crc_flagged():
    frame = bytearray(_frame(0x80000, 0x60000))
    frame[6] ^= 0xFF  # corrupt the CRC byte
    _, _, _, crc_ok = aht20.decode(bytes(frame))
    assert crc_ok is False


def test_short_frame_raises():
    import pytest

    with pytest.raises(ValueError):
        aht20.decode(b"\x00\x00\x00")
