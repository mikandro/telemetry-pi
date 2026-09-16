"""Psychrometric helpers: absolute humidity and dew point.

Pure functions over (temperature in Celsius, relative humidity in percent).
Used by the ventilation advisor to compare indoor vs outdoor moisture in
absolute terms. See docs/ventilation-advisor.md.
"""

from __future__ import annotations

import math

# Magnus formula coefficients (over water, valid roughly -45..60 C).
_A = 17.62
_B = 243.12  # deg C
_ES0 = 6.112  # hPa, saturation vapour pressure at 0 C
# g/m3 per (hPa / K): 100 * M_w / R = 216.68
_AH_CONST = 216.7


def saturation_vapour_pressure(t_c: float) -> float:
    """Saturation vapour pressure over water, in hPa."""
    return _ES0 * math.exp(_A * t_c / (_B + t_c))


def absolute_humidity(t_c: float, rh_pct: float) -> float:
    """Absolute humidity in grams of water per cubic metre of air."""
    e = saturation_vapour_pressure(t_c) * (rh_pct / 100.0)
    return _AH_CONST * e / (t_c + 273.15)


def dew_point(t_c: float, rh_pct: float) -> float:
    """Dew point temperature in Celsius (Magnus approximation)."""
    # Clamp RH away from 0 so the log is finite.
    rh = max(min(rh_pct, 100.0), 0.01)
    alpha = math.log(rh / 100.0) + _A * t_c / (_B + t_c)
    return _B * alpha / (_A - alpha)
