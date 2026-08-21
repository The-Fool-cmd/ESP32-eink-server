import json
import os
import urllib.parse
import urllib.request
from datetime import datetime
from urllib.error import URLError

_TIMEOUT = 10
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# "NOW" plus this many hours ahead in the hourly forecast strip.
_HOURLY_SPAN = 6

# WMO weather codes (Open-Meteo's `weather_code`), collapsed to short
# HUD-style labels and one of a handful of pure-CSS icon shapes (see
# templates/widgets/weather.html's .icon-* classes — no emoji/webfont, so
# rendering never depends on a color-emoji font being present). Codes not
# listed here fall back to "UNKNOWN" / icon-cloudy rather than raising. See
# https://open-meteo.com/en/docs for the full table.
_CONDITIONS = {
    0: ("CLEAR", "clear"),
    1: ("MOSTLY CLEAR", "clear"),
    2: ("PARTLY CLOUDY", "cloudy"),
    3: ("OVERCAST", "cloudy"),
    45: ("FOG", "fog"),
    48: ("FOG", "fog"),
    51: ("LIGHT DRIZZLE", "rain"),
    53: ("DRIZZLE", "rain"),
    55: ("HEAVY DRIZZLE", "rain"),
    56: ("FREEZING DRIZZLE", "rain"),
    57: ("FREEZING DRIZZLE", "rain"),
    61: ("LIGHT RAIN", "rain"),
    63: ("RAIN", "rain"),
    65: ("HEAVY RAIN", "rain"),
    66: ("FREEZING RAIN", "rain"),
    67: ("FREEZING RAIN", "rain"),
    71: ("LIGHT SNOW", "snow"),
    73: ("SNOW", "snow"),
    75: ("HEAVY SNOW", "snow"),
    77: ("SNOW GRAINS", "snow"),
    80: ("RAIN SHOWERS", "rain"),
    81: ("RAIN SHOWERS", "rain"),
    82: ("HEAVY SHOWERS", "rain"),
    85: ("SNOW SHOWERS", "snow"),
    86: ("SNOW SHOWERS", "snow"),
    95: ("THUNDERSTORM", "storm"),
    96: ("THUNDERSTORM", "storm"),
    99: ("THUNDERSTORM", "storm"),
}

_COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def _condition(code: int) -> tuple[str, str]:
    return _CONDITIONS.get(code, ("UNKNOWN", "cloudy"))


def _compass(deg: float) -> str:
    return _COMPASS[round(deg / 45) % 8]


def _uv_category(uv: float) -> tuple[str, str]:
    """WHO's 5-tier UV scale collapsed to 3 status levels — SPECTRA6 has no
    orange/violet, so High/Very High/Extreme all map to the same "high" red
    (see templates/widgets/weather.html's .uv-* classes). The text label
    always ships alongside the color, same "never color-alone" rule as the
    uptime status tiles in screen_status.html.
    """
    if uv < 3:
        return "LOW", "low"
    if uv < 6:
        return "MODERATE", "moderate"
    if uv < 8:
        return "HIGH", "high"
    if uv < 11:
        return "VERY HIGH", "high"
    return "EXTREME", "high"


def _fmt_time(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%H:%M")


def _fetch_json(url: str, params: dict) -> dict:
    with urllib.request.urlopen(f"{url}?{urllib.parse.urlencode(params)}", timeout=_TIMEOUT) as resp:
        return json.loads(resp.read())


def get_context(lat: str | None = None, lon: str | None = None, now: datetime | None = None) -> dict:
    lat = lat or os.environ.get("WEATHER_LAT")
    lon = lon or os.environ.get("WEATHER_LON")
    now = now or datetime.now()
    # Own key, not calendar.py's "date_label" — both would be merged into
    # the same context dict in server.py, and a same-named key from two
    # widgets silently collides (last ctx.update() wins) rather than erroring.
    date_label = now.strftime("%a %d %b").upper()

    if not lat or not lon:
        return {"weather_error": "Location not configured", "weather_date_label": date_label}

    location_name = os.environ.get("WEATHER_LOCATION_NAME") or f"{lat}, {lon}"

    # forecast_days=2 (not 1): the hourly strip below needs "now" plus the
    # next _HOURLY_SPAN hours, which can roll past midnight into tomorrow
    # depending what time the device happens to render at — a 1-day window
    # would run out of hours for a render that lands late in the evening.
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,weather_code",
        "hourly": "temperature_2m,precipitation_probability,relative_humidity_2m",
        "daily": (
            "uv_index_max,wind_speed_10m_max,wind_gusts_10m_max,wind_direction_10m_dominant,"
            "precipitation_probability_max,sunrise,sunset"
        ),
        "timezone": "auto",
        "forecast_days": 2,
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
    }

    try:
        data = _fetch_json(_FORECAST_URL, params)

        current = data["current"]
        hourly = data["hourly"]
        daily = data["daily"]

        now_condition, now_icon = _condition(current["weather_code"])

        # Index of the current hour in the hourly arrays — floor "now" to
        # the hour and find that exact timestamp, rather than assuming
        # index 0 (forecast_days=2 always starts its arrays at today's
        # 00:00, not "now").
        now_key = now.strftime("%Y-%m-%dT%H:00")
        times = hourly["time"]
        now_idx = times.index(now_key) if now_key in times else 0

        hourly_temps = hourly["temperature_2m"][now_idx : now_idx + _HOURLY_SPAN + 1]
        hourly_precip = hourly["precipitation_probability"][now_idx : now_idx + _HOURLY_SPAN + 1]
        hourly_labels = ["NOW"] + [
            datetime.fromisoformat(t).strftime("%H") for t in times[now_idx + 1 : now_idx + _HOURLY_SPAN + 1]
        ]
        # Bars are scaled within this 7-point window's own min/max, not the
        # full day's — the strip is a near-term glance, not a day overview,
        # so its own range gives more visible bar-height variation.
        span_low, span_high = min(hourly_temps), max(hourly_temps)
        span = (span_high - span_low) or 1
        hourly_bars = [
            {
                "label": label,
                "temp": round(t),
                "precip": round(p),
                "bar_pct": round(((t - span_low) / span) * 100),
            }
            for label, t, p in zip(hourly_labels, hourly_temps, hourly_precip)
        ]

        # "Peak" rain chance today, and the hour it hits — today's 24 hours
        # are always indices 0-23 (forecast_days=2 puts today first).
        precip_peak = daily["precipitation_probability_max"][0]
        today_precip = hourly["precipitation_probability"][:24]
        peak_idx = today_precip.index(precip_peak) if precip_peak in today_precip else 0
        precip_peak_hour = datetime.fromisoformat(times[peak_idx]).strftime("%H:00")

        today_humidity = hourly["relative_humidity_2m"][:24]
        humidity_avg = round(sum(today_humidity) / len(today_humidity))

        uv_label, uv_level = _uv_category(daily["uv_index_max"][0])

        return {
            "weather_error": None,
            "weather_date_label": date_label,
            "location_name": location_name.upper(),
            "now_temp": round(current["temperature_2m"]),
            "now_condition": now_condition,
            "now_icon": now_icon,
            "hourly_bars": hourly_bars,
            "precip_peak": round(precip_peak),
            "precip_peak_hour": precip_peak_hour,
            "uv_index": round(daily["uv_index_max"][0], 1),
            "uv_label": uv_label,
            "uv_level": uv_level,
            "wind_max": round(daily["wind_speed_10m_max"][0]),
            "wind_gust": round(daily["wind_gusts_10m_max"][0]),
            "wind_dir": _compass(daily["wind_direction_10m_dominant"][0]),
            "wind_dir_deg": round(daily["wind_direction_10m_dominant"][0]),
            "humidity_avg": humidity_avg,
            "humidity_segments": round(humidity_avg / 10),
            "sunrise": _fmt_time(daily["sunrise"][0]),
            "sunset": _fmt_time(daily["sunset"][0]),
        }
    # Broad on purpose, same posture as widgets/calendar.py and
    # widgets/uptime.py: a bad response shape (missing key, empty array,
    # malformed JSON) degrades to the "unavailable" widget state rather than
    # failing the whole render.
    except (URLError, OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        return {"weather_error": str(exc), "weather_date_label": date_label}
