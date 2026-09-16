"""Outdoor conditions from the Open-Meteo API (free, no API key).

Provides current outdoor temperature and relative humidity for the advisor,
cached with a TTL so the collector loop mostly reads memory and only hits the
network occasionally. Degrades gracefully: on error it keeps the last good
value, or returns None if it never succeeded.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from typing import Callable, Optional, Tuple

log = logging.getLogger("collector.weather")

# Munich; override via --lat/--lon.
DEFAULT_LAT = 48.137
DEFAULT_LON = 11.575

Outdoor = Tuple[float, float]  # (temp_c, rh_pct)


def fetch_open_meteo(lat: float, lon: float, timeout: float = 8.0) -> Outdoor:
    """One live fetch. Raises on network/parse errors."""
    params = urllib.parse.urlencode(
        {"latitude": lat, "longitude": lon, "current": "temperature_2m,relative_humidity_2m"}
    )
    url = f"https://api.open-meteo.com/v1/forecast?{params}"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        data = json.load(resp)
    cur = data["current"]
    return float(cur["temperature_2m"]), float(cur["relative_humidity_2m"])


class OutdoorSource:
    """TTL-cached outdoor conditions. `fetch_fn` is injectable for tests."""

    def __init__(
        self,
        lat: float = DEFAULT_LAT,
        lon: float = DEFAULT_LON,
        ttl_s: float = 600.0,
        fetch_fn: Optional[Callable[[float, float], Outdoor]] = None,
    ) -> None:
        self.lat = lat
        self.lon = lon
        self.ttl_s = ttl_s
        self._fetch_fn = fetch_fn or fetch_open_meteo
        self._value: Optional[Outdoor] = None
        self._fetched_at: float = 0.0

    def current(self) -> Optional[Outdoor]:
        """Return cached conditions, refreshing if older than the TTL."""
        if self._value is None or (time.monotonic() - self._fetched_at) > self.ttl_s:
            try:
                self._value = self._fetch_fn(self.lat, self.lon)
                self._fetched_at = time.monotonic()
                log.debug("outdoor conditions: %s", self._value)
            except Exception as exc:  # keep the last good value on failure
                log.warning("outdoor fetch failed (%s); using cached=%s", exc, self._value)
        return self._value
