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
    lookback_windows = list(dict.fromkeys((lookback_days, max(365, lookback_days))))
    result = None
    start = end
    for days in lookback_windows:
        start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        result = await search_scenes(
            bbox=bbox,
            start_date=start,
            end_date=end,
            collections=["sentinel-2-l2a", "landsat-c2-l2"],
            max_cloud=35.0,
            limit=15,
        )
        if result.get("success") and result.get("scenes"):
            break
        if result.get("success") is False:
            break
    if not result or not result.get("success") or not result.get("scenes"):
        return {
            "success": False,
            "error": (
                result.get("error") if result and not result.get("success")
                else "No suitable optical scenes found in the extended lookback window"
            ),
            "reason": "No cloud-filtered optical acquisition is available for this AOI in the searched date ranges.",
            "date_range": [start, end],
            "source": result.get("source"),
            "search_result": result,
        }
    # Prefer Sentinel-2, then clearer and newer scenes for safe retrieval fallbacks.
    scenes = result["scenes"]
    s2 = [s for s in scenes if "sentinel-2" in (s.get("collection") or "")]
    candidates = s2 or scenes
    candidates = sorted(
        candidates,
        key=lambda s: (
            s.get("cloud_cover_pct") if s.get("cloud_cover_pct") is not None else 999,
            -(int((s.get("acquisition_date") or "0000-00-00").replace("-", ""))),
        ),
    )
    chosen = candidates[0]
    return {
        "success": True,
        "scene": chosen,
        "candidates": candidates[:3],
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


async def get_best_scene_near_date(
    bbox: List[float],
    target_date: str,
    window_days: int = 14,
    collections: Optional[List[str]] = None,
    max_cloud: float = 40.0,
) -> Dict[str, Any]:
    """
    Find the best optical scene near a specific date (target_date ± window_days).
    Returns real STAC metadata only; never invents a scene.
    """
    if collections is None:
        collections = ["sentinel-2-l2a", "landsat-c2-l2"]
    try:
        center = datetime.strptime(target_date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return {
            "success": False,
            "error": f"Invalid date: {target_date}. Use YYYY-MM-DD.",
            "requested_date": target_date,
        }
    start = (center - timedelta(days=window_days)).strftime("%Y-%m-%d")
    end = (center + timedelta(days=window_days)).strftime("%Y-%m-%d")
    result = await search_scenes(
        bbox=bbox,
        start_date=start,
        end_date=end,
        collections=collections,
        max_cloud=max_cloud,
        limit=20,
    )
    if not result.get("success") or not result.get("scenes"):
        return {
            "success": False,
            "error": f"No suitable optical scene found near {target_date}",
            "reason": (
                f"No low-cloud optical acquisition in [{start}, {end}] for this AOI. "
                "Try a wider window or a different date."
            ),
            "requested_date": target_date,
            "search_window": [start, end],
            "source": result.get("source", "Microsoft Planetary Computer STAC"),
            "scenes_found": 0,
        }

    def _date_dist(scene: Dict[str, Any]) -> float:
        d = scene.get("datetime") or scene.get("acquired") or ""
        try:
            sd = datetime.fromisoformat(str(d).replace("Z", "+00:00"))
            if sd.tzinfo is None:
                sd = sd.replace(tzinfo=timezone.utc)
            return abs((sd - center).total_seconds())
        except Exception:
            return 1e18

    scenes = result["scenes"]
    s2 = [s for s in scenes if "sentinel-2" in (s.get("collection") or "")]
    pool = s2 if s2 else scenes
    chosen = min(
        pool,
        key=lambda s: (
            _date_dist(s),
            s.get("cloud_cover_pct") if s.get("cloud_cover_pct") is not None else 999,
        ),
    )
    return {
        "success": True,
        "scene": chosen,
        "requested_date": target_date,
        "search_window": [start, end],
        "search_meta": {
            "scene_count": result.get("scene_count"),
            "source": result.get("source"),
        },
    }


async def compare_scenes_by_dates(
    bbox: List[float],
    date_a: str,
    date_b: str,
    window_days: int = 14,
    max_cloud: float = 40.0,
    index: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch best scenes for Date A and Date B and return side-by-side metadata.
    Optional index name (ndvi/ndwi/ndbi) is recorded for UI; full raster differencing
    requires COG access and is reported honestly when unavailable.
    """
    scene_a = await get_best_scene_near_date(bbox, date_a, window_days, max_cloud=max_cloud)
    scene_b = await get_best_scene_near_date(bbox, date_b, window_days, max_cloud=max_cloud)

    both_ok = scene_a.get("success") and scene_b.get("success")
    out: Dict[str, Any] = {
        "success": both_ok,
        "date_a": date_a,
        "date_b": date_b,
        "bbox": bbox,
        "scene_a": scene_a.get("scene") if scene_a.get("success") else None,
        "scene_b": scene_b.get("scene") if scene_b.get("success") else None,
        "meta_a": {
            "success": scene_a.get("success"),
            "error": scene_a.get("error"),
            "reason": scene_a.get("reason"),
            "requested_date": date_a,
            "search_window": scene_a.get("search_window"),
            "source": (scene_a.get("search_meta") or {}).get("source") or scene_a.get("source"),
        },
        "meta_b": {
            "success": scene_b.get("success"),
            "error": scene_b.get("error"),
            "reason": scene_b.get("reason"),
            "requested_date": date_b,
            "search_window": scene_b.get("search_window"),
            "source": (scene_b.get("search_meta") or {}).get("source") or scene_b.get("source"),
        },
        "index_requested": index,
        "difference": None,
        "message": None,
    }

    if not scene_a.get("success") and not scene_b.get("success"):
        out["message"] = (
            f"No scenes found near {date_a} or {date_b}. "
            "Widen the date window or choose different dates."
        )
    elif not scene_a.get("success"):
        out["message"] = f"Scene A unavailable: {scene_a.get('error') or scene_a.get('reason')}"
    elif not scene_b.get("success"):
        out["message"] = f"Scene B unavailable: {scene_b.get('error') or scene_b.get('reason')}"
    else:
        sa = scene_a["scene"]
        sb = scene_b["scene"]
        out["message"] = (
            f"Found scenes near both dates. "
            f"A: {sa.get('datetime') or sa.get('acquired')} "
            f"(cloud {sa.get('cloud_cover_pct')}%, {sa.get('collection')}). "
            f"B: {sb.get('datetime') or sb.get('acquired')} "
            f"(cloud {sb.get('cloud_cover_pct')}%, {sb.get('collection')})."
        )
        if index:
            out["difference"] = {
                "index": index.lower(),
                "status": "metadata_only",
                "note": (
                    "Full raster index difference requires reachable COG band reads for both scenes. "
                    "Metadata comparison is complete; pixel-level Δ is not invented when rasters are unavailable."
                ),
            }

    return out


async def available_years_for_aoi(
    bbox: List[float],
    collections: Optional[List[str]] = None,
    max_cloud: float = 80.0,
    min_year: int = 2015,
    max_year: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Dynamically discover years that have at least one optical scene over the AOI.
    Uses STAC; never returns a fabricated static list.
    """
    if collections is None:
        collections = ["sentinel-2-l2a", "landsat-c2-l2"]
    if max_year is None:
        max_year = datetime.now(timezone.utc).year

    years_found: set = set()
    # Probe each year with a light search (limit small) — honest about empty years
    for year in range(min_year, max_year + 1):
        start = f"{year}-01-01"
        end = f"{year}-12-31"
        try:
            result = await search_scenes(
                bbox=bbox,
                start_date=start,
                end_date=end,
                collections=collections,
                max_cloud=max_cloud,
                limit=5,
            )
            if result.get("success") and result.get("scenes"):
                years_found.add(year)
        except Exception as e:
            logger.warning(f"available_years probe {year} failed: {e}")
            continue

    years = sorted(years_found)
    return {
        "success": True,
        "years": years,
        "min_year": years[0] if years else None,
        "max_year": years[-1] if years else None,
        "bbox": bbox,
        "collections": collections,
        "source": "Microsoft Planetary Computer STAC",
        "note": "Only years with at least one matching scene are listed. Empty years are omitted.",
    }


async def get_best_scene_for_year(
    bbox: List[float],
    year: int,
    preferred_month: int = 6,
    preferred_day: int = 15,
    window_days: int = 45,
    collections: Optional[List[str]] = None,
    max_cloud: float = 40.0,
) -> Dict[str, Any]:
    """
    Best optical scene in a given calendar year, preferring mid-year (or preferred date).
    """
    target = f"{year:04d}-{preferred_month:02d}-{preferred_day:02d}"
    # Clamp target into year
    try:
        datetime.strptime(target, "%Y-%m-%d")
    except ValueError:
        target = f"{year:04d}-06-15"
    # First try mid-year window; if empty, widen to full year
    result = await get_best_scene_near_date(
        bbox, target, window_days=window_days, collections=collections, max_cloud=max_cloud
    )
    if result.get("success"):
        result["requested_year"] = year
        return result
    # Full-year fallback
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    if collections is None:
        collections = ["sentinel-2-l2a", "landsat-c2-l2"]
    search = await search_scenes(
        bbox=bbox, start_date=start, end_date=end,
        collections=collections, max_cloud=max_cloud, limit=20,
    )
    if not search.get("success") or not search.get("scenes"):
        return {
            "success": False,
            "error": f"No suitable optical scene found for year {year}",
            "reason": f"No low-cloud optical acquisition in {year} for this AOI.",
            "requested_year": year,
            "search_window": [start, end],
            "source": search.get("source", "Microsoft Planetary Computer STAC"),
            "scenes_found": 0,
        }
    scenes = search["scenes"]
    s2 = [s for s in scenes if "sentinel-2" in (s.get("collection") or "")]
    pool = s2 if s2 else scenes
    chosen = min(
        pool,
        key=lambda s: s.get("cloud_cover_pct") if s.get("cloud_cover_pct") is not None else 999,
    )
    return {
        "success": True,
        "scene": chosen,
        "requested_year": year,
        "search_window": [start, end],
        "search_meta": {
            "scene_count": search.get("scene_count"),
            "source": search.get("source"),
        },
    }


def _scene_summary(scene: Optional[Dict[str, Any]], requested: Any) -> Dict[str, Any]:
    if not scene:
        return {"success": False, "requested": requested}
    assets = scene.get("assets") or []
    if isinstance(assets, dict):
        assets = list(assets.keys())
    return {
        "success": True,
        "requested": requested,
        "acquisition_date": scene.get("acquisition_date") or scene.get("datetime") or scene.get("acquired"),
        "satellite": scene.get("satellite") or scene.get("platform"),
        "platform": scene.get("platform"),
        "sensor": scene.get("sensor"),
        "collection": scene.get("collection"),
        "cloud_cover_pct": scene.get("cloud_cover_pct"),
        "scene_id": scene.get("id"),
        "id": scene.get("id"),
        "available_bands": assets,
        "bbox": scene.get("bbox"),
    }


async def compare_scenes_by_years(
    bbox: List[float],
    year_a: int,
    year_b: int,
    max_cloud: float = 40.0,
    index: Optional[str] = None,
    collections: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Year-to-year comparison using best available scene in each year."""
    scene_a = await get_best_scene_for_year(bbox, int(year_a), collections=collections, max_cloud=max_cloud)
    scene_b = await get_best_scene_for_year(bbox, int(year_b), collections=collections, max_cloud=max_cloud)
    both_ok = scene_a.get("success") and scene_b.get("success")
    sa = scene_a.get("scene") if scene_a.get("success") else None
    sb = scene_b.get("scene") if scene_b.get("success") else None
    out: Dict[str, Any] = {
        "success": both_ok,
        "mode": "year_to_year",
        "year_a": year_a,
        "year_b": year_b,
        "bbox": bbox,
        "scene_a": sa,
        "scene_b": sb,
        "summary_a": _scene_summary(sa, year_a),
        "summary_b": _scene_summary(sb, year_b),
        "meta_a": {
            "success": scene_a.get("success"),
            "error": scene_a.get("error"),
            "reason": scene_a.get("reason"),
            "requested_year": year_a,
            "search_window": scene_a.get("search_window"),
            "source": (scene_a.get("search_meta") or {}).get("source") or scene_a.get("source"),
        },
        "meta_b": {
            "success": scene_b.get("success"),
            "error": scene_b.get("error"),
            "reason": scene_b.get("reason"),
            "requested_year": year_b,
            "search_window": scene_b.get("search_window"),
            "source": (scene_b.get("search_meta") or {}).get("source") or scene_b.get("source"),
        },
        "index_requested": index,
        "difference": None,
        "message": None,
    }
    if not scene_a.get("success") and not scene_b.get("success"):
        out["message"] = f"No scenes found for {year_a} or {year_b}."
    elif not scene_a.get("success"):
        out["message"] = f"Year A ({year_a}) unavailable: {scene_a.get('error') or scene_a.get('reason')}"
    elif not scene_b.get("success"):
        out["message"] = f"Year B ({year_b}) unavailable: {scene_b.get('error') or scene_b.get('reason')}"
    else:
        out["message"] = (
            f"Found scenes for {year_a} and {year_b}. "
            f"A: {out['summary_a'].get('acquisition_date')} "
            f"(cloud {out['summary_a'].get('cloud_cover_pct')}%, {out['summary_a'].get('collection')}). "
            f"B: {out['summary_b'].get('acquisition_date')} "
            f"(cloud {out['summary_b'].get('cloud_cover_pct')}%, {out['summary_b'].get('collection')})."
        )
        if index:
            out["difference"] = {
                "index": index.lower(),
                "status": "metadata_only",
                "note": (
                    "Full raster index difference requires reachable COG band reads. "
                    "Metadata comparison is complete; pixel-level Δ is not invented."
                ),
            }
    return out
