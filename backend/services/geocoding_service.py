"""
Real geocoding via OpenStreetMap Nominatim using geopy.
No fabricated coordinates.
"""

from typing import Any, Dict, Iterable, List
from geopy.geocoders import Nominatim

from backend.config import get_settings
from backend.utils.cache import cache_get, cache_set, make_cache_key
from backend.utils.logging import logger
from backend.utils.validation import parse_coordinates, AOI


USER_AGENT = "SatQueryAI/1.0 (educational project)"


def _normalize_query(query: str) -> str:
    """Normalize harmless formatting differences before querying Nominatim."""
    return ", ".join(
        part.strip()
        for part in " ".join((query or "").split()).split(",")
        if part.strip()
    )


def _fallback_queries(query: str) -> List[str]:
    """Build a small, conservative set of alternate place-name queries."""
    parts = [part.strip() for part in query.split(",") if part.strip()]
    candidates: List[str] = []

    if len(parts) > 1:
        candidates.append(", ".join(parts))
    if parts:
        candidates.append(parts[0])
    if len(parts) == 1:
        candidates.append(f"{parts[0]}, Tamil Nadu")
    elif len(parts) == 2 and parts[1].lower() not in {"tamil nadu", "india"}:
        candidates.append(f"{parts[0]}, Tamil Nadu, India")

    # Correct common accidental repeated letters without maintaining a city list.
    for variant in _remove_one_repeated_letter(parts[0] if parts else query):
        suffix = ", ".join(parts[1:])
        candidates.append(f"{variant}, {suffix}" if suffix else variant)

    return list(dict.fromkeys(candidate for candidate in candidates if candidate and candidate != query))


def _remove_one_repeated_letter(value: str) -> Iterable[str]:
    """Yield variants formed by removing one character from a repeated run."""
    variants = []
    for index in range(len(value) - 1):
        if value[index].lower() == value[index + 1].lower():
            variants.append(value[:index] + value[index + 1:])
    return variants


async def geocode(query: str) -> Dict[str, Any]:
    """
    Resolve a place name or coordinates to a location + AOI.
    """

    settings = get_settings()
    query = _normalize_query(query)

    if not query:
        return {
            "success": False,
            "error": "Empty location query",
            "source": "validation",
        }

    # ---------------------------------------------------------
    # 1. Direct coordinates
    # ---------------------------------------------------------
    coords = parse_coordinates(query)

    if coords:
        lat, lon = coords

        aoi = _buffer_aoi(
            lat,
            lon,
            settings.DEFAULT_AOI_BUFFER_KM
        )

        return {
            "success": True,
            "query": query,
            "display_name": f"{lat:.5f}, {lon:.5f}",
            "lat": lat,
            "lon": lon,
            "latitude": lat,
            "longitude": lon,
            "bbox": aoi.bbox(),
            "aoi": aoi.model_dump(),
            "aoi_area_km2": round(aoi.area_approx_km2(), 2),
            "place_type": "coordinates",
            "source": "user_coordinates",
            "source_url": None,
            "attribution": "User-provided coordinates",
        }

    # ---------------------------------------------------------
    # 2. Cache
    # ---------------------------------------------------------
    cache_key = make_cache_key("geocode", query.lower())

    cached = cache_get(
        cache_key,
        ttl=settings.CACHE_TTL_GEOCODING
    )

    if cached:
        cached["from_cache"] = True
        return cached

    # ---------------------------------------------------------
    # 3. Geopy + Nominatim
    # ---------------------------------------------------------
    try:
        geolocator = Nominatim(
            user_agent=USER_AGENT,
            timeout=20
        )

        location = None
        attempted_queries = [query, *_fallback_queries(query)]
        for candidate in attempted_queries:
            location = await _geocode_async(geolocator, candidate)
            if location is not None:
                break

    except Exception as e:
        logger.error(f"Geocoding error: {e}")

        return {
            "success": False,
            "error": f"Geocoding service unavailable: {type(e).__name__}",
            "source": "Nominatim (OpenStreetMap)",
            "query": query,
        }

    if location is None:
        return {
            "success": False,
            "error": f"No location found for '{query}'",
            "source": "Nominatim (OpenStreetMap)",
            "query": query,
        }

    # ---------------------------------------------------------
    # 4. Coordinates
    # ---------------------------------------------------------
    lat = float(location.latitude)
    lon = float(location.longitude)

    # ---------------------------------------------------------
    # 5. AOI
    # ---------------------------------------------------------
    aoi = _buffer_aoi(
        lat,
        lon,
        settings.DEFAULT_AOI_BUFFER_KM
    )

    # Limit AOI size
    if aoi.area_approx_km2() > settings.MAX_AOI_AREA_KM2:
        aoi = _buffer_aoi(
            lat,
            lon,
            min(
                settings.DEFAULT_AOI_BUFFER_KM,
                15.0
            )
        )

    # ---------------------------------------------------------
    # 6. Result
    # ---------------------------------------------------------
    result = {
        "success": True,
        "query": query,
        "display_name": location.address,
        "lat": lat,
        "lon": lon,
        "latitude": lat,
        "longitude": lon,
        "bbox": aoi.bbox(),
        "aoi": aoi.model_dump(),
        "aoi_area_km2": round(
            aoi.area_approx_km2(),
            2
        ),
        "place_type": "place",
        "source": "Nominatim (OpenStreetMap)",
        "source_url": "https://nominatim.openstreetmap.org",
        "attribution": "© OpenStreetMap contributors",
        "from_cache": False,
        "alternatives": [],
    }

    cache_set(
        cache_key,
        result,
        ttl=settings.CACHE_TTL_GEOCODING
    )

    return result


async def _geocode_async(
    geolocator: Nominatim,
    query: str
):
    """
    Run geopy's blocking geocode call without blocking
    the FastAPI event loop.
    """

    import asyncio

    loop = asyncio.get_running_loop()

    return await loop.run_in_executor(
        None,
        lambda: geolocator.geocode(
            query,
            exactly_one=True
        )
    )


def _buffer_aoi(
    lat: float,
    lon: float,
    buffer_km: float
) -> AOI:

    import math

    dlat = buffer_km / 111.0

    dlon = buffer_km / (
        111.0 *
        max(
            0.2,
            math.cos(
                math.radians(lat)
            )
        )
    )

    return AOI(
        min_lat=lat - dlat,
        max_lat=lat + dlat,
        min_lon=lon - dlon,
        max_lon=lon + dlon,
    )


async def reverse_geocode(
    lat: float,
    lon: float
) -> Dict[str, Any]:

    try:

        geolocator = Nominatim(
            user_agent=USER_AGENT,
            timeout=20
        )

        location = await _reverse_async(
            geolocator,
            lat,
            lon
        )

        if location is None:
            return {
                "success": False,
                "error": "Location not found",
                "lat": lat,
                "lon": lon,
            }

        return {
            "success": True,
            "display_name": location.address,
            "lat": lat,
            "lon": lon,
            "latitude": lat,
            "longitude": lon,
            "source": "Nominatim (OpenStreetMap)",
        }

    except Exception as e:

        logger.error(
            f"Reverse geocoding error: {e}"
        )

        return {
            "success": False,
            "error": str(e),
            "lat": lat,
            "lon": lon,
        }


async def _reverse_async(
    geolocator: Nominatim,
    lat: float,
    lon: float
):

    import asyncio

    loop = asyncio.get_running_loop()

    return await loop.run_in_executor(
        None,
        lambda: geolocator.reverse(
            (lat, lon),
            exactly_one=True
        )
    )