"""Tests for psychrometric helpers."""

from collector.psychro import absolute_humidity, dew_point, saturation_vapour_pressure


def test_saturation_vapour_pressure_at_zero():
    assert round(saturation_vapour_pressure(0.0), 3) == 6.112


def test_absolute_humidity_known_values():
    # 21 C / 55% RH is about 10.0 g/m3; 6 C / 82% is about 5.9 g/m3.
    assert abs(absolute_humidity(21.0, 55.0) - 10.05) < 0.15
    assert abs(absolute_humidity(6.0, 82.0) - 5.95) < 0.15


def test_absolute_humidity_monotonic_in_rh():
    assert absolute_humidity(21.0, 30.0) < absolute_humidity(21.0, 70.0)


def test_dew_point_known_value():
    assert abs(dew_point(21.0, 55.0) - 11.6) < 0.3


def test_dew_point_equals_temp_at_saturation():
    # At 100% RH the dew point is the air temperature.
    assert abs(dew_point(20.0, 100.0) - 20.0) < 0.2
