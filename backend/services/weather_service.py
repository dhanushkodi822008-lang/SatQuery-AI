"""
Real weather data via Open-Meteo (free, no API key required).
https://open-meteo.com/
Provides current conditions, recent rainfall, and forecast.
"""
from typing import Any, Dict, Optional
from datetime import datetime, timezone
import httpx
from backend.config import get_settings
from backend.utils.cache import cache_get, cache_set, make_cache_key
from backend.utils.logging import logger


async def get_weather(lat: float, lon: float) -> Dict[str, Any]:
    """
    Fetch current weather + daily forecast for a location.
    All values come from Open-Meteo; nothing is invented.
    """
    settings = get_settings()
    cache_key = make_cache_key("weather", round(lat, 3), round(lon, 3))
    cached = cache_get(cache_key, ttl=settings.CACHE_TTL_WEATHER)
    if cached:
        cached["from_cache"] = True
        return cached

    # Forecast request (forward-looking) with past_days for observed hourly slots
    forecast_url = f"{settings.OPEN_METEO_URL}/forecast"
    forecast_params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m,wind_direction_10m,cloud_cover",
        "hourly": "precipitation,temperature_2m",
        "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto",
        "forecast_days": 5,
        "past_days": 2,
    }

    # Archive API for confirmed observed daily rainfall (preferred for last_24h)
    archive_url = "https://archive-api.open-meteo.com/v1/archive"
    from datetime import timedelta as _td
    end_d = datetime.now(timezone.utc).date()
    start_d = end_d - _td(days=2)
    archive_params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_d.isoformat(),
        "end_date": end_d.isoformat(),
        "daily": "precipitation_sum",
        "timezone": "auto",
    }

    data = {}
    archive_data = {}
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.get(forecast_url, params=forecast_params)
            resp.raise_for_status()
            data = resp.json()
            try:
                aresp = await client.get(archive_url, params=archive_params)
                if aresp.status_code == 200:
                    archive_data = aresp.json()
            except Exception as ae:
                logger.warning(f"Open-Meteo archive (observed rainfall) unavailable: {ae}")
    except Exception as e:
        logger.error(f"Open-Meteo error: {e}")
        return {
            "success": False,
            "error": f"Weather service unavailable: {type(e).__name__}",
            "source": "Open-Meteo",
            "lat": lat,
            "lon": lon,
        }

    current = data.get("current", {})
    daily = data.get("daily", {})
    hourly = data.get("hourly", {})
    hourly_times = hourly.get("time") or []
    hourly_precip = hourly.get("precipitation") or []

    # Observed last ~24h rainfall (NOT forecast)
    precip_24h = None
    precip_24h_source = None
    archive_daily = (archive_data.get("daily") or {})
    archive_dates = archive_daily.get("time") or []
    archive_precip = archive_daily.get("precipitation_sum") or []
    if archive_dates and archive_precip:
        today_str = end_d.isoformat()
        observed_vals = []
        for d, p in zip(archive_dates, archive_precip):
            if p is None:
                continue
            if d < today_str:
                observed_vals.append(float(p))
        if observed_vals:
            precip_24h = round(observed_vals[-1], 2)
            precip_24h_source = "Open-Meteo Archive (previous complete day precipitation_sum)"
        elif archive_precip[-1] is not None:
            precip_24h = round(float(archive_precip[-1]), 2)
            precip_24h_source = "Open-Meteo Archive (latest daily precipitation_sum)"

    if precip_24h is None and hourly_times and hourly_precip:
        now = datetime.now(timezone.utc)
        past_vals = []
        for t_str, p in zip(hourly_times, hourly_precip):
            if p is None:
                continue
            try:
                t = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                if t <= now:
                    past_vals.append(float(p))
            except Exception:
                continue
        if past_vals:
            precip_24h = round(sum(past_vals[-24:]), 2)
            precip_24h_source = "Open-Meteo past hourly precipitation (observed slots only)"

    # Forecast next 3 days — today and future daily sums only
    daily_precip = daily.get("precipitation_sum") or []
    daily_dates = daily.get("time") or []
    forecast_vals = []
    today_str = datetime.now(timezone.utc).date().isoformat()
    for d, p in zip(daily_dates, daily_precip):
        if p is None:
            continue
        if d >= today_str:
            forecast_vals.append(float(p))
    forecast_precip_3d = round(sum(forecast_vals[:3]), 2) if forecast_vals else None

    result = {
        "success": True,
        "lat": lat,
        "lon": lon,
        "source": "Open-Meteo",
        "source_url": "https://open-meteo.com/",
        "attribution": "Weather data by Open-Meteo.com",
        "data_type": "NEAR REAL-TIME",
        "updated_at": current.get("time") or datetime.now(timezone.utc).isoformat(),
        "timezone": data.get("timezone"),
        "current": {
            "temperature_c": current.get("temperature_2m"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "precipitation_mm": current.get("precipitation"),
            "weather_code": current.get("weather_code"),
            "weather_description": _wmo_code_to_text(current.get("weather_code")),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "wind_direction_deg": current.get("wind_direction_10m"),
            "cloud_cover_pct": current.get("cloud_cover"),
            "observed_at": current.get("time"),
        },
        "rainfall": {
            "last_24h_mm": precip_24h,
            "last_24h_source": precip_24h_source,
            "forecast_next_3d_mm": forecast_precip_3d,
            "daily_forecast_mm": daily_precip[:5] if daily_precip else [],
            "daily_dates": daily_dates[:5] if daily_dates else [],
            "note": (
                "last_24h_mm is observed/historical rainfall when available; "
                "forecast_next_3d_mm is forward-looking forecast only. Never mixed."
            ),
        },
        "daily_forecast": {
            "dates": daily_dates[:5] if daily_dates else [],
            "temp_max_c": (daily.get("temperature_2m_max") or [])[:5],
            "temp_min_c": (daily.get("temperature_2m_min") or [])[:5],
            "precip_mm": daily_precip[:5] if daily_precip else [],
            "precip_prob_max": (daily.get("precipitation_probability_max") or [])[:5],
        },
        "from_cache": False,
        "note": "Air temperature (2 m), not satellite land-surface temperature.",
    }
    cache_set(cache_key, result, ttl=settings.CACHE_TTL_WEATHER)
    return result


def _wmo_code_to_text(code: Optional[int]) -> str:
    if code is None:
        return "Unknown"
    mapping = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }
    return mapping.get(code, f"WMO code {code}")
