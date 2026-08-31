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

    url = f"{settings.OPEN_METEO_URL}/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m,wind_direction_10m,cloud_cover",
        "hourly": "precipitation,temperature_2m",
        "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto",
        "forecast_days": 5,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
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

    # Recent 24h rainfall from hourly if available
    precip_24h = None
    if hourly.get("precipitation"):
        precip_vals = hourly["precipitation"][:24]
        precip_24h = round(sum(p for p in precip_vals if p is not None), 2)

    # Forecast rainfall next 3 days
    daily_precip = daily.get("precipitation_sum") or []
    forecast_precip_3d = round(sum(p for p in daily_precip[:3] if p is not None), 2) if daily_precip else None

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
            "forecast_next_3d_mm": forecast_precip_3d,
            "daily_forecast_mm": daily_precip[:5] if daily_precip else [],
            "daily_dates": (daily.get("time") or [])[:5],
        },
        "daily_forecast": {
            "dates": (daily.get("time") or [])[:5],
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
