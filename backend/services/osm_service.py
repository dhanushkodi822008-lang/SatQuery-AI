"""
OpenStreetMap / Overpass for named water bodies, rivers, lakes.
Used to enrich satellite water extent with authoritative names where available.
"""
from typing import Any, Dict, List
import httpx
from backend.config import get_settings
from backend.utils.logging import logger

USER_AGENT = "SatQueryAI/1.0 (SIH2026 educational prototype)"


async def get_water_features(bbox: List[float], limit: int = 50) -> Dict[str, Any]:
    """
    Query Overpass for waterways and natural=water features inside bbox.
    bbox: [min_lon, min_lat, max_lon, max_lat]
    """
    settings = get_settings()
    min_lon, min_lat, max_lon, max_lat = bbox
    # Overpass QL
    query = f"""
    [out:json][timeout:25];
    (
      way["waterway"~"river|stream|canal"]({min_lat},{min_lon},{max_lat},{max_lon});
      relation["waterway"~"river"]({min_lat},{min_lon},{max_lat},{max_lon});
      way["natural"="water"]({min_lat},{min_lon},{max_lat},{max_lon});
      relation["natural"="water"]({min_lat},{min_lon},{max_lat},{max_lon});
      way["landuse"="reservoir"]({min_lat},{min_lon},{max_lat},{max_lon});
    );
    out tags center {limit};
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                settings.OVERPASS_URL,
                data={"data": query},
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"Overpass error: {e}")
        return {
            "success": False,
            "error": f"OSM Overpass unavailable: {type(e).__name__}",
            "source": "OpenStreetMap Overpass API",
            "features": [],
        }

    features = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:en")
        if not name and not tags.get("waterway") and not tags.get("natural"):
            continue
        center = el.get("center") or {}
        features.append({
            "osm_id": el.get("id"),
            "osm_type": el.get("type"),
            "name": name or tags.get("waterway") or tags.get("natural") or "unnamed water feature",
            "waterway": tags.get("waterway"),
            "natural": tags.get("natural"),
            "landuse": tags.get("landuse"),
            "lat": center.get("lat"),
            "lon": center.get("lon"),
            "tags": {k: v for k, v in tags.items() if k in ("name", "waterway", "natural", "landuse", "intermittent")},
        })

    return {
        "success": True,
        "source": "OpenStreetMap (Overpass API)",
        "source_url": "https://www.openstreetmap.org",
        "attribution": "© OpenStreetMap contributors",
        "feature_count": len(features),
        "features": features,
        "note": "Names come from OSM community mapping; not from satellite classification.",
    }
