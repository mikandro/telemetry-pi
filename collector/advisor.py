"""Ventilation advisor: should you open the window right now?

Pure decision logic over indoor and (optional) outdoor conditions. All I/O
(fetching outdoor weather) lives in collector.weather; this module just decides,
so it is trivially testable. See docs/ventilation-advisor.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from .psychro import absolute_humidity, dew_point

# States (also used as Grafana value-mapping keys and Pico ring colours).
COMFORTABLE = "comfortable"
VENTILATE = "ventilate"
KEEP_CLOSED = "keep_closed"
UNKNOWN = "unknown"


@dataclass
class AdvisorConfig:
    target_rh: float = 50.0   # below this indoors: nothing to do
    mold_rh: float = 60.0     # at/above this indoors: raise mold_risk
    ah_margin: float = 0.5    # g/m3 hysteresis: outdoor must be this much drier


@dataclass
class Advice:
    ventilation_state: str
    should_ventilate: int
    mold_risk: int
    indoor_abs_humidity_gm3: float
    dew_point_c: float
    outdoor_abs_humidity_gm3: Optional[float]
    outdoor_temp_c: Optional[float]
    outdoor_humidity_pct: Optional[float]

    def as_reading_fields(self) -> dict:
        """The subset of collector.metrics.Reading fields this populates."""
        return {
            "outdoor_temp_c": self.outdoor_temp_c,
            "outdoor_humidity_pct": self.outdoor_humidity_pct,
            "indoor_abs_humidity_gm3": round(self.indoor_abs_humidity_gm3, 3),
            "outdoor_abs_humidity_gm3": (
                None if self.outdoor_abs_humidity_gm3 is None
                else round(self.outdoor_abs_humidity_gm3, 3)
            ),
            "dew_point_c": round(self.dew_point_c, 2),
            "ventilation_state": self.ventilation_state,
            "should_ventilate": self.should_ventilate,
            "mold_risk": self.mold_risk,
        }


class Advisor:
    def __init__(self, config: Optional[AdvisorConfig] = None) -> None:
        self.config = config or AdvisorConfig()

    def evaluate(
        self,
        indoor_t_c: float,
        indoor_rh_pct: float,
        outdoor: Optional[Tuple[float, float]],
    ) -> Advice:
        """`outdoor` is (temp_c, rh_pct) or None when no outdoor data."""
        cfg = self.config
        indoor_ah = absolute_humidity(indoor_t_c, indoor_rh_pct)
        dew = dew_point(indoor_t_c, indoor_rh_pct)
        mold = 1 if indoor_rh_pct >= cfg.mold_rh else 0

        outdoor_ah: Optional[float] = None
        out_t: Optional[float] = None
        out_rh: Optional[float] = None

        if outdoor is None:
            state, should = UNKNOWN, 0
        else:
            out_t, out_rh = outdoor
            outdoor_ah = absolute_humidity(out_t, out_rh)
            if indoor_rh_pct <= cfg.target_rh:
                state, should = COMFORTABLE, 0
            elif outdoor_ah < indoor_ah - cfg.ah_margin:
                state, should = VENTILATE, 1
            else:
                state, should = KEEP_CLOSED, 0

        return Advice(
            ventilation_state=state,
            should_ventilate=should,
            mold_risk=mold,
            indoor_abs_humidity_gm3=indoor_ah,
            dew_point_c=dew,
            outdoor_abs_humidity_gm3=outdoor_ah,
            outdoor_temp_c=out_t,
            outdoor_humidity_pct=out_rh,
        )
