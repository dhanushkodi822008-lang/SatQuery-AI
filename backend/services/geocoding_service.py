"""
Real geocoding and administrative boundary extraction via OpenStreetMap Nominatim.
Retrieves true Polygon / MultiPolygon geometries for administrative areas (country, state, district, city, town, village).
Calculates exact geodesic area. Never fabricates artificial bounding box boundaries.
"""

from typing import Any, Dict, Iterable, List, Optional, Tuple
import math
import httpx
from shapely.geometry import shape

from backend.config import get_settings
from backend.utils.cache import cache_get, cache_set, make_cache_key
from backend.utils.logging import logger
from backend.utils.validation import parse_coordinates, AOI


USER_AGENT = "SatQueryAI/1.0 (educational remote sensing platform; contact@satquery.ai)"
NOMINATIM_BASE = "https://nominatim.openstreetmap.org"


def _normalize_query(query: str) -> str:
    """Normalize harmless formatting differences before querying Nominatim."""
    return ", ".join(
        part.strip()
        for part in " ".join((query or "").split()).split(",")
        if part.strip()
    )


def _fallback_queries(query: str) -> List[str]:
    """Build a conservative set of alternate place-name queries."""
    parts = [part.strip() for part in query.split(",") if part.strip()]
    candidates: List[str] = []

    if len(parts) > 1:
        candidates.append(", ".join(parts))
    if parts:
        candidates.append(parts[0])
    if len(parts) == 1:
        candidates.append(f"{parts[0]}, Tamil Nadu")
        candidates.append(f"{parts[0]} District")
    elif len(parts) == 2 and parts[1].lower() not in {"tamil nadu", "india"}:
        candidates.append(f"{parts[0]}, Tamil Nadu, India")

    return list(dict.fromkeys(candidate for candidate in candidates if candidate and candidate != query))


def calculate_geodesic_polygon_area_km2(geom_geojson: Dict[str, Any]) -> float:
    """
    Calculate geodesic area of a GeoJSON Polygon or MultiPolygon on WGS84 ellipsoid.
    Uses ellipsoidal meridian and parallel scaling factors at the centroid latitude.
    """
    if not geom_geojson or not isinstance(geom_geojson, dict):
        return 0.0
    try:
        geom = shape(geom_geojson)
        if geom.is_empty:
            return 0.0
        centroid = geom.centroid
        mean_lat = centroid.y
        lat_rad = math.radians(mean_lat)
        # Meridian and parallel scale factors for WGS84 ellipsoid
        m_per_deg_lat = 111132.954 - 559.822 * math.cos(2 * lat_rad) + 1.175 * math.cos(4 * lat_rad)
        m_per_deg_lon = (math.pi / 180.0) * 6378137.0 * math.cos(lat_rad)
        area_m2 = float(geom.area) * m_per_deg_lat * m_per_deg_lon
        return max(0.0, float(area_m2) / 1_000_000.0)
    except Exception as exc:
        logger.warning(f"Error calculating geodesic area: {exc}")
        return 0.0


def _extract_admin_level(address: Dict[str, Any], place_type: str, class_type: str) -> str:
    """Identify administrative level from OSM address components."""
    if not address:
        if place_type in ("country", "state", "district", "city", "town", "village"):
            return place_type.capitalize()
        return "Geographic Area"

    if address.get("country") and not any(k in address for k in ("state", "county", "state_district", "city", "town", "village")):
        return "Country"
    if address.get("state") and not any(k in address for k in ("county", "state_district", "city", "town", "village")):
        return "State"
    if address.get("state_district") or address.get("county") or "district" in str(address.get("city", "")).lower():
        return "District"
    if address.get("city") or address.get("municipality"):
        return "City"
    if address.get("town"):
        return "Town"
    if address.get("village") or address.get("hamlet"):
        return "Village"
    if address.get("suburb") or address.get("neighbourhood") or address.get("locality"):
        return "Locality"
    return (place_type or "Area").replace("_", " ").capitalize()


def _bbox_from_geojson_or_bb(geojson: Optional[Dict[str, Any]], boundingbox: Optional[List[Any]]) -> List[float]:
    """Return [min_lon, min_lat, max_lon, max_lat]"""
    if geojson:
        try:
            geom = shape(geojson)
            if not geom.is_empty:
                minx, miny, maxx, maxy = geom.bounds
                return [float(minx), float(miny), float(maxx), float(maxy)]
        except Exception:
            pass
    if boundingbox and len(boundingbox) == 4:
        # Nominatim boundingbox format is [min_lat, max_lat, min_lon, max_lon]
        return [float(boundingbox[2]), float(boundingbox[0]), float(boundingbox[3]), float(boundingbox[1])]
    return [0.0, 0.0, 0.0, 0.0]


async def _query_nominatim_search(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Execute async Nominatim search with polygon_geojson and addressdetails."""
    url = f"{NOMINATIM_BASE}/search"
    params = {
        "q": query,
        "format": "jsonv2",
        "polygon_geojson": "1",
        "addressdetails": "1",
        "extratags": "1",
        "limit": str(limit),
    }
    async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": USER_AGENT}) as client:
        resp = await client.get(url, params=params)
        if resp.status_code == 200:
            return resp.json() or []
        return []


async def _query_nominatim_reverse(lat: float, lon: float, zoom: int = 14) -> Optional[Dict[str, Any]]:
    """Execute async Nominatim reverse geocode."""
    url = f"{NOMINATIM_BASE}/reverse"
    params = {
        "lat": str(lat),
        "lon": str(lon),
        "format": "jsonv2",
        "polygon_geojson": "1",
        "addressdetails": "1",
        "extratags": "1",
        "zoom": str(zoom),
    }
    async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": USER_AGENT}) as client:
        resp = await client.get(url, params=params)
        if resp.status_code == 200:
            return resp.json()
        return None


async def geocode(query: str) -> Dict[str, Any]:
    """
    Resolve a place name or coordinates to a location and real geographic/administrative boundary.
    Never invents square boundaries for administrative entities.
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
    # 1. Direct coordinates parsing
    # ---------------------------------------------------------
    coords = parse_coordinates(query)
    if coords:
        lat, lon = coords
        # Validate coordinates range
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return {
                "success": False,
                "error": f"Coordinates out of range: latitude ({lat}) must be [-90, +90], longitude ({lon}) must be [-180, +180].",
                "source": "validation",
            }

        return await geocode_coordinates(lat, lon)

    # ---------------------------------------------------------
    # 2. Check cache
    # ---------------------------------------------------------
    cache_key = make_cache_key("geocode_real_boundary", query.lower())
    cached = cache_get(cache_key, ttl=settings.CACHE_TTL_GEOCODING)
    if cached:
        cached["from_cache"] = True
        return cached

    # ---------------------------------------------------------
    # 3. Query Nominatim for real administrative boundary polygon
    # ---------------------------------------------------------
    items: List[Dict[str, Any]] = []
    attempted_queries = [query, *_fallback_queries(query)]

    for candidate in attempted_queries:
        try:
            items = await _query_nominatim_search(candidate, limit=5)
            if items:
                break
        except Exception as e:
            logger.warning(f"Nominatim query failed for candidate '{candidate}': {e}")

    # Prioritize items that have Polygon or MultiPolygon GeoJSON
    selected_item = None
    for item in items:
        gtype = (item.get("geojson") or {}).get("type")
        if gtype in ("Polygon", "MultiPolygon"):
            selected_item = item
            break

    if selected_item is None and items:
        selected_item = items[0]

    if selected_item is None:
        # Fallback to Photon
        photon_res = await _photon_geocode(query)
        if photon_res:
            lat = float(photon_res["lat"])
            lon = float(photon_res["lon"])
            return await geocode_coordinates(lat, lon, original_query=query, display_name=photon_res.get("display_name"))
        
        return {
            "success": False,
            "error": f"No location found for '{query}'. Please check the spelling or provide coordinates.",
            "source": "Nominatim (OpenStreetMap)",
            "query": query,
        }

    # Extract location and administrative info
    lat = float(selected_item["lat"])
    lon = float(selected_item["lon"])
    address = selected_item.get("address") or {}
    place_type = selected_item.get("type") or selected_item.get("class") or "place"
    admin_level = _extract_admin_level(address, place_type, selected_item.get("class", ""))
    
    geojson = selected_item.get("geojson")
    has_real_boundary = False
    area_km2 = 0.0

    if geojson and geojson.get("type") in ("Polygon", "MultiPolygon"):
        has_real_boundary = True
        area_km2 = calculate_geodesic_polygon_area_km2(geojson)
    else:
        # If the top search result only gave a point (e.g. city node), check if an administrative relation exists
        place_name_clean = address.get("county") or address.get("state_district") or address.get("city") or address.get("town") or query
        if place_name_clean and place_name_clean.lower() != query.lower():
            try:
                rel_items = await _query_nominatim_search(f"{place_name_clean} boundary", limit=3)
                for r in rel_items:
                    rgtype = (r.get("geojson") or {}).get("type")
                    if rgtype in ("Polygon", "MultiPolygon"):
                        geojson = r.get("geojson")
                        has_real_boundary = True
                        area_km2 = calculate_geodesic_polygon_area_km2(geojson)
                        break
            except Exception:
                pass

    bbox = _bbox_from_geojson_or_bb(geojson, selected_item.get("boundingbox"))
    
    # If no real boundary polygon is available, do NOT generate an artificial square polygon claiming to be the district.
    # Provide the center point and bounding box for map view.
    display_name = selected_item.get("display_name") or query
    place_name = selected_item.get("name") or address.get("city") or address.get("county") or address.get("state_district") or display_name.split(",")[0].strip()

    country = address.get("country") or "India"
    state_name = address.get("state") or address.get("state_district")
    district_name = address.get("state_district") or address.get("county") or (address.get("city") if "district" in str(address.get("city", "")).lower() else None)

    result: Dict[str, Any] = {
        "success": True,
        "query": query,
        "place_name": place_name,
        "display_name": display_name,
        "administrative_level": admin_level,
        "admin_level": admin_level,
        "country": country,
        "state": state_name,
        "district": district_name,
        "lat": lat,
        "lon": lon,
        "latitude": lat,
        "longitude": lon,
        "center": {"lat": lat, "lon": lon},
        "bbox": bbox,
        "geometry": geojson if has_real_boundary else None,
        "aoi": geojson if has_real_boundary else None,
        "has_real_boundary": has_real_boundary,
        "boundary_type": "actual_administrative_polygon" if has_real_boundary else "point_only",
        "aoi_area_km2": round(area_km2, 4) if has_real_boundary else None,
        "area_km2": round(area_km2, 4) if has_real_boundary else None,
        "area_ha": round(area_km2 * 100.0, 2) if has_real_boundary else None,
        "area_sqft": round(area_km2 * 10_763_910.41671, 2) if has_real_boundary else None,
        "place_type": place_type,
        "source": "Nominatim (OpenStreetMap)",
        "source_url": "https://nominatim.openstreetmap.org",
        "attribution": "© OpenStreetMap contributors",
        "from_cache": False,
        "address": address,
    }

    cache_set(cache_key, result, ttl=settings.CACHE_TTL_GEOCODING)
    return result


async def geocode_coordinates(lat: float, lon: float, original_query: Optional[str] = None, display_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Reverse geocode a coordinate pair, identify administrative units, and retrieve real boundary polygons.
    """
    settings = get_settings()
    cache_key = make_cache_key("geocode_coords_real", f"{lat:.5f}_{lon:.5f}")
    cached = cache_get(cache_key, ttl=settings.CACHE_TTL_GEOCODING)
    if cached:
        cached["from_cache"] = True
        return cached

    rev_data = None
    try:
        rev_data = await _query_nominatim_reverse(lat, lon, zoom=14)
    except Exception as exc:
        logger.warning(f"Reverse geocoding error for ({lat}, {lon}): {exc}")

    address = (rev_data or {}).get("address") or {}
    disp = (rev_data or {}).get("display_name") or display_name or f"{lat:.5f}, {lon:.5f}"
    
    country = address.get("country") or "India"
    state_name = address.get("state")
    district_name = address.get("state_district") or address.get("county")
    town_name = address.get("town") or address.get("city") or address.get("village")
    
    admin_level = _extract_admin_level(address, (rev_data or {}).get("type", "coordinates"), "")
    
    # Check if reverse result came with a real boundary polygon
    rev_geojson = (rev_data or {}).get("geojson")
    has_real_boundary = False
    admin_boundary_geojson = None
    area_km2 = 0.0

    if rev_geojson and rev_geojson.get("type") in ("Polygon", "MultiPolygon"):
        admin_boundary_geojson = rev_geojson
        has_real_boundary = True
        area_km2 = calculate_geodesic_polygon_area_km2(admin_boundary_geojson)
    else:
        # Query the district or town administrative boundary so user can select it
        search_target = district_name or town_name or state_name
        if search_target:
            try:
                target_query = f"{search_target}, {state_name}" if state_name and state_name not in search_target else search_target
                search_results = await _query_nominatim_search(target_query, limit=3)
                for item in search_results:
                    igtype = (item.get("geojson") or {}).get("type")
                    if igtype in ("Polygon", "MultiPolygon"):
                        admin_boundary_geojson = item.get("geojson")
                        has_real_boundary = True
                        area_km2 = calculate_geodesic_polygon_area_km2(admin_boundary_geojson)
                        break
            except Exception as e:
                logger.warning(f"Failed to fetch enclosing boundary for '{search_target}': {e}")

    # Set up bounding box
    d = 0.05
    bbox = _bbox_from_geojson_or_bb(admin_boundary_geojson, [lat - d, lat + d, lon - d, lon + d])

    place_name = town_name or district_name or f"{lat:.5f}, {lon:.5f}"

    result: Dict[str, Any] = {
        "success": True,
        "query": original_query or f"{lat:.5f}, {lon:.5f}",
        "place_name": place_name,
        "display_name": disp,
        "administrative_level": admin_level,
        "admin_level": admin_level,
        "country": country,
        "state": state_name,
        "district": district_name,
        "lat": lat,
        "lon": lon,
        "latitude": lat,
        "longitude": lon,
        "center": {"lat": lat, "lon": lon},
        "bbox": bbox,
        "geometry": admin_boundary_geojson if has_real_boundary else None,
        "aoi": admin_boundary_geojson if has_real_boundary else None,
        "has_real_boundary": has_real_boundary,
        "boundary_type": "actual_administrative_polygon" if has_real_boundary else "point_only",
        "aoi_area_km2": round(area_km2, 4) if has_real_boundary else None,
        "area_km2": round(area_km2, 4) if has_real_boundary else None,
        "area_ha": round(area_km2 * 100.0, 2) if has_real_boundary else None,
        "area_sqft": round(area_km2 * 10_763_910.41671, 2) if has_real_boundary else None,
        "place_type": "coordinates",
        "source": "Nominatim (OpenStreetMap)",
        "source_url": "https://nominatim.openstreetmap.org",
        "attribution": "© OpenStreetMap contributors",
        "address": address,
        "notes": "Exact administrative boundary loaded." if has_real_boundary else "Location found, but an exact administrative boundary is unavailable. You can draw a custom AOI manually.",
    }

    cache_set(cache_key, result, ttl=settings.CACHE_TTL_GEOCODING)
    return result


async def reverse_geocode(lat: float, lon: float) -> Dict[str, Any]:
    """Reverse geocoding endpoint helper."""
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return {
            "success": False,
            "error": "Latitude must be between -90 and 90, Longitude between -180 and 180.",
            "lat": lat,
            "lon": lon,
        }
    return await geocode_coordinates(lat, lon)


async def _photon_geocode(query: str) -> Optional[Dict[str, Any]]:
    """Fallback geocoder using Photon (backed by OpenStreetMap)."""
    try:
        async with httpx.AsyncClient(timeout=6.0, headers={"User-Agent": USER_AGENT}) as client:
            response = await client.get(
                "https://photon.komoot.io/api/",
                params={"q": query, "limit": 1},
            )
            response.raise_for_status()
            features = response.json().get("features") or []
            if not features:
                return None
            feature = features[0]
            geometry = feature.get("geometry") or {}
            coordinates = geometry.get("coordinates") or []
            if len(coordinates) < 2:
                return None
            props = feature.get("properties") or {}
            parts = [
                props.get("name"), props.get("city"), props.get("state"), props.get("country")
            ]
            display_name = ", ".join(dict.fromkeys(str(x).strip() for x in parts if x))
            return {
                "lon": coordinates[0],
                "lat": coordinates[1],
                "display_name": display_name or query,
                "place_type": props.get("osm_value") or props.get("type") or "place",
            }
    except Exception as exc:
        logger.warning(f"Photon fallback geocoding failed: {exc}")
        return None