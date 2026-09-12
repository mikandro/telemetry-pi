# AHT20 / DHT20 measurement-frame decoding.
#
# Pure, dependency-free Python so it runs unchanged under both CPython (for the
# unit tests in tests/test_aht20.py) and MicroPython (imported by main.py on the
# Pico). Keep it free of type hints and f-strings that MicroPython may not like.


def crc8(data):
    """Dallas/Maxim CRC-8 (poly 0x31, init 0xFF), as the AHT20 datasheet uses."""
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x31) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def decode(data):
    """Decode a 7-byte AHT20 measurement frame.

    Layout: [status, hum[19:12], hum[11:4], hum[3:0]|temp[19:16], temp[15:8],
    temp[7:0], crc]. Returns (temp_c, humidity_pct, busy, crc_ok).
    """
    if len(data) < 7:
        raise ValueError("AHT20 frame needs 7 bytes")

    status = data[0]
    busy = bool(status & 0x80)

    hum_raw = (data[1] << 12) | (data[2] << 4) | (data[3] >> 4)
    temp_raw = ((data[3] & 0x0F) << 16) | (data[4] << 8) | data[5]

    humidity_pct = hum_raw * 100.0 / 1048576.0          # /2**20
    temp_c = temp_raw * 200.0 / 1048576.0 - 50.0

    crc_ok = crc8(data[0:6]) == data[6]
    return temp_c, humidity_pct, busy, crc_ok
