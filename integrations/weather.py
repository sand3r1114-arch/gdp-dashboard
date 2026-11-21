"""Weer via Open-Meteo (gratis, geen account of sleutel nodig)."""

from __future__ import annotations

from integrations.http import get_json

# WMO-weercodes -> (omschrijving, icoon)
WMO = {
    0: ("Onbewolkt", "☀️"), 1: ("Overwegend helder", "🌤️"), 2: ("Half bewolkt", "⛅"), 3: ("Bewolkt", "☁️"),
    45: ("Mist", "🌫️"), 48: ("Mist met rijp", "🌫️"),
    51: ("Lichte motregen", "🌦️"), 53: ("Motregen", "🌦️"), 55: ("Zware motregen", "🌧️"),
    56: ("IJzel", "🧊"), 57: ("Zware ijzel", "🧊"),
    61: ("Lichte regen", "🌦️"), 63: ("Regen", "🌧️"), 65: ("Zware regen", "🌧️"),
    66: ("IJzel", "🧊"), 67: ("Zware ijzel", "🧊"),
    71: ("Lichte sneeuw", "🌨️"), 73: ("Sneeuw", "🌨️"), 75: ("Zware sneeuw", "❄️"), 77: ("Sneeuwkorrels", "🌨️"),
    80: ("Lichte buien", "🌦️"), 81: ("Buien", "🌧️"), 82: ("Zware buien", "⛈️"),
    85: ("Sneeuwbuien", "🌨️"), 86: ("Zware sneeuwbuien", "❄️"),
    95: ("Onweer", "⛈️"), 96: ("Onweer met hagel", "⛈️"), 99: ("Zwaar onweer met hagel", "⛈️"),
}


def describe(code: int | None) -> tuple[str, str]:
    return WMO.get(int(code) if code is not None else -1, ("Onbekend", "🌡️"))


def geocode(name: str) -> dict | None:
    """Zoek een plaats op (eerst in Nederland). Geeft {'name', 'lat', 'lon', 'region'} of None."""
    for country in ("NL", None):
        params = {"name": name, "count": 1, "language": "nl", "format": "json"}
        if country:
            params["countryCode"] = country
        data = get_json("https://geocoding-api.open-meteo.com/v1/search", params)
        if data.get("results"):
            r = data["results"][0]
            return {"name": r["name"], "lat": r["latitude"], "lon": r["longitude"],
                    "region": r.get("admin1") or r.get("country", "")}
    return None


def forecast(lat: float, lon: float) -> dict:
    return get_json("https://api.open-meteo.com/v1/forecast", {
        "latitude": lat, "longitude": lon, "timezone": "Europe/Amsterdam", "forecast_days": 3,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,precipitation,relative_humidity_2m",
        "hourly": "temperature_2m,precipitation,weather_code",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
    })
