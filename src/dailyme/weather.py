"""The weather box, from Open-Meteo's free forecast API (no key needed)."""

from __future__ import annotations

import json
import urllib.request
from urllib.parse import urlencode

from . import USER_AGENT
from .models import Weather
from .profile import Location

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes, as used by Open-Meteo.
WMO = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Freezing fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    56: "Freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Rain showers",
    81: "Rain showers",
    82: "Violent rain showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorms",
    96: "Thunderstorms with hail",
    99: "Thunderstorms with hail",
}


def describe(code: int | None) -> str:
    return WMO.get(code if code is not None else -1, "Forecast unavailable")


def forecast(location: Location, *, timeout: float = 10.0) -> Weather | None:
    """Today's forecast for the reader's location, or None if it isn't available."""
    if location.latitude is None or location.longitude is None:
        return None
    query = urlencode(
        {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "daily": "weather_code,temperature_2m_max,temperature_2m_min",
            "timezone": "auto",
            "forecast_days": 1,
        }
    )
    request = urllib.request.Request(f"{FORECAST_URL}?{query}", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            daily = json.load(response).get("daily") or {}
    except Exception:  # noqa: BLE001 - no weather box is better than no paper
        return None

    def first(key: str) -> float | None:
        values = daily.get(key) or [None]
        return values[0]

    code = first("weather_code")
    return Weather(
        place=location.name or "Today",
        summary=describe(int(code) if code is not None else None),
        high_c=first("temperature_2m_max"),
        low_c=first("temperature_2m_min"),
    )
