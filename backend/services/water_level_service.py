"""
River / gauge water-level service.
For Indian rivers (e.g. Cauvery), public machine-readable live gauge APIs are limited.
This service attempts known open sources and honestly reports when no station data is available.
Never fabricates water levels in metres from satellite imagery.
"""
from typing import Any, Dict, List, Optional
import httpx
from backend.utils.logging import logger


# Known public / open hydrological endpoints (extendable)
# India CWC does not provide a simple open REST API for arbitrary stations.
# We document the limitation clearly.


async def get_water_level(lat: float, lon: float, place_name: str = "") -> Dict[str, Any]:
    """
    Attempt to retrieve measured river water level near the location.
    Returns structured 'unavailable' response when no trusted source exists.
    """
    # Attempt 1: Open-Meteo does not provide river levels.
    # Attempt 2: Global Flood Awareness System / other open APIs are complex.
    # For this prototype we check a placeholder registry of known stations
    # and return honest unavailability for most Indian locations.

    known = _lookup_known_station(lat, lon, place_name)
    if known:
        # If we had a live endpoint we would call it here.
        # Currently no free public live feed is wired for CWC stations.
        return {
            "success": False,
            "available": False,
            "message": (
                "Live measured water-level data is not available for this location "
                "from the connected sources."
            ),
            "reason": "No authenticated public gauge API connected for this station",
            "nearest_station_hint": known,
            "lat": lat,
            "lon": lon,
            "source": "SatQuery AI water-level registry",
            "data_type": "UNAVAILABLE",
            "note": (
                "Satellite-derived water *extent* (area) is different from gauge-measured "
                "water *level* (height in metres). Do not confuse the two."
            ),
        }

    return {
        "success": False,
        "available": False,
        "message": (
            "Live measured water-level data is not available for this location "
            "from the connected sources."
        ),
        "reason": "No river gauge station found in connected sources for this AOI",
        "lat": lat,
        "lon": lon,
        "source": None,
        "data_type": "UNAVAILABLE",
        "note": (
            "Satellite water extent (km²) can still be computed from imagery. "
            "Gauge water level (m) requires an official hydrometric station feed."
        ),
        "how_to_add": (
            "To enable real gauge data: obtain API access from Central Water Commission (CWC) "
            "or state irrigation department, then configure WATER_GAUGE_API_URL and credentials "
            "in .env and implement the fetch in this service."
        ),
    }


def _lookup_known_station(lat: float, lon: float, place_name: str) -> Optional[Dict]:
    """Static hints for well-known rivers (not live levels)."""
    name_lower = (place_name or "").lower()
    if "cauvery" in name_lower or "kaveri" in name_lower or "karur" in name_lower:
        return {
            "river": "Cauvery (Kaveri)",
            "hint": "CWC / Tamil Nadu WRD operate gauges along Cauvery; public API not connected.",
            "reference": "https://indiawris.gov.in/ or CWC flood forecasting",
        }
    if "chennai" in name_lower or "cooum" in name_lower or "adyar" in name_lower:
        return {
            "river": "Chennai basin rivers",
            "hint": "Local corporation / PWD gauges; no open API connected.",
        }
    return None
