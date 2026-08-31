"""
Satellite Data Provider abstraction.
Searches real STAC catalogs (Microsoft Planetary Computer) for Sentinel-2, Landsat, Sentinel-1.
Never invents scenes or dates.
"""
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone
import httpx
from backend.config import get_settings
from backend.utils.cache import cache_get, cache_set, make_cache_key
from backend.utils.logging import logger

# Planetary Computer STAC collections
COLLECTIONS = {
    "sentinel-2-l2a": {
        "name": "Sentinel-2 L2A",
        "sensor": "MSI",
        "platform": "Sentinel-2",
        "resolution_m": 10,
        "type": "optical",
    },
    "landsat-c2-l2": {
        "name": "Landsat Collection 2 Level-2",
        "sensor": "OLI/TIRS",
        "platform": "Landsat",
        "resolution_m": 30,
        "type": "optical",
    },
    "sentinel-1-rtc": {
        "name": "Sentinel-1 RTC",
        "sensor": "C-SAR",
        "platform": "Sentinel-1",
        "resolution_m": 10,
        "type": "sar",
    },
}


async def search_scenes(
    bbox: List[float],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    collections: Optional[List[str]] = None,
    max_cloud: float = 40.0,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Search Planetary Computer STAC for available scenes over AOI.
    Returns real scene metadata only.
    """
    settings = get_settings()
    if collections is None:
        collections = ["sentinel-2-l2a", "landsat-c2-l2"]

    if end_date is None:
        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if start_date is None:
        start_dt = datetime.now(timezone.utc) - timedelta(days=settings.DEFAULT_LOOKBACK_DAYS)
        start_date = start_dt.strftime("%Y-%m-%d")

    cache_key = make_cache_key(
        "stac_search", tuple(round(x, 4) for x in bbox), start_date, end_date,
        tuple(collections), max_cloud, limit
    )
    cached = cache_get(cache_key, ttl=settings.CACHE_TTL_SATELLITE_SEARCH)
    if cached:
        cached["from_cache"] = True
        return cached

    stac_url = settings.PLANETARY_COMPUTER_STAC
    search_body = {
        "collections": collections,
        "bbox": bbox,
        "datetime": f"{start_date}T00:00:00Z/{end_date}T23:59:59Z",
        "limit": limit,
        "query": {},
    }
    # Cloud cover filter for optical only
    if any(c in ("sentinel-2-l2a", "landsat-c2-l2") for c in collections):
        search_body["query"]["eo:cloud_cover"] = {"lt": max_cloud}

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(f"{stac_url}/search", json=search_body)
            if resp.status_code == 400:
                # Retry without query filter (some collections differ)
                search_body.pop("query", None)
                resp = await client.post(f"{stac_url}/search", json=search_body)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"STAC search error: {e}")
        return {
            "success": False,
            "error": f"Satellite catalog search failed: {type(e).__name__}: {e}",
            "source": "Microsoft Planetary Computer STAC",
            "scenes": [],
            "bbox": bbox,
            "date_range": [start_date, end_date],
        }

    features = data.get("features", [])
    scenes = []
    for f in features:
        props = f.get("properties", {})
        coll = f.get("collection", "")
        meta = COLLECTIONS.get(coll, {})
        cloud = props.get("eo:cloud_cover")
        if cloud is not None and cloud > max_cloud and meta.get("type") == "optical":
            continue
        scenes.append({
            "id": f.get("id"),
            "collection": coll,
            "satellite": meta.get("platform") or coll,
            "sensor": meta.get("sensor"),
            "resolution_m": meta.get("resolution_m"),
            "type": meta.get("type", "unknown"),
            "acquisition_date": (props.get("datetime") or "")[:10],
            "datetime": props.get("datetime"),
            "cloud_cover_pct": cloud,
            "platform": props.get("platform"),
            "instruments": props.get("instruments"),
            "processing_level": props.get("processing:level") or props.get("landsat:correction") or "L2A",
            "bbox": f.get("bbox"),
            "assets": list((f.get("assets") or {}).keys()),
            "stac_item": f,  # keep for later asset signing if needed
        })

    # Sort by date descending
    scenes.sort(key=lambda s: s.get("acquisition_date") or "", reverse=True)

    latest = scenes[0] if scenes else None
    result = {
        "success": True,
        "source": "Microsoft Planetary Computer STAC",
        "source_url": "https://planetarycomputer.microsoft.com/",
        "attribution": "Data from ESA Copernicus / USGS / Microsoft Planetary Computer",
        "bbox": bbox,
        "date_range": [start_date, end_date],
        "max_cloud_cover": max_cloud,
        "scene_count": len(scenes),
        "scenes": scenes,
        "latest_available": {
            "acquisition_date": latest["acquisition_date"] if latest else None,
            "satellite": latest["satellite"] if latest else None,
            "sensor": latest["sensor"] if latest else None,
            "cloud_cover_pct": latest.get("cloud_cover_pct") if latest else None,
            "collection": latest["collection"] if latest else None,
            "id": latest["id"] if latest else None,
        } if latest else None,
        "note": (
            "Satellites do not acquire every location every day. "
            "Shown dates are actual acquisition times from the catalog. "
            "No imagery is invented for the current day if none exists."
        ),
        "from_cache": False,
    }
    cache_set(cache_key, result, ttl=settings.CACHE_TTL_SATELLITE_SEARCH)
    return result


async def get_best_optical_scene(bbox: List[float], lookback_days: int = 90) -> Dict[str, Any]:
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    result = await search_scenes(
        bbox=bbox,
        start_date=start,
        end_date=end,
        collections=["sentinel-2-l2a", "landsat-c2-l2"],
        max_cloud=35.0,
        limit=15,
    )
    if not result.get("success") or not result.get("scenes"):
        return {
            "success": False,
            "error": "No suitable optical scenes found in the lookback window",
            "reason": "No cloud-free or low-cloud optical acquisition available for this AOI in the selected period",
            "date_range": [start, end],
            "source": result.get("source"),
            "search_result": result,
        }
    # Prefer Sentinel-2, then lowest cloud
    scenes = result["scenes"]
    s2 = [s for s in scenes if "sentinel-2" in (s.get("collection") or "")]
    chosen = None
    if s2:
        chosen = min(s2, key=lambda s: s.get("cloud_cover_pct") if s.get("cloud_cover_pct") is not None else 999)
    else:
        chosen = min(scenes, key=lambda s: s.get("cloud_cover_pct") if s.get("cloud_cover_pct") is not None else 999)
    return {
        "success": True,
        "scene": chosen,
        "search_meta": {
            "scene_count": result["scene_count"],
            "date_range": result["date_range"],
            "source": result["source"],
        },
    }


async def get_best_sar_scene(bbox: List[float], lookback_days: int = 60) -> Dict[str, Any]:
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    result = await search_scenes(
        bbox=bbox,
        start_date=start,
        end_date=end,
        collections=["sentinel-1-rtc"],
        max_cloud=100.0,  # N/A for SAR
        limit=10,
    )
    if not result.get("success") or not result.get("scenes"):
        return {
            "success": False,
            "error": "No Sentinel-1 SAR scenes found",
            "reason": "No SAR acquisition available for this AOI in the lookback window",
            "date_range": [start, end],
            "source": result.get("source"),
        }
    return {
        "success": True,
        "scene": result["scenes"][0],
        "search_meta": {
            "scene_count": result["scene_count"],
            "date_range": result["date_range"],
            "source": result["source"],
        },
    }
