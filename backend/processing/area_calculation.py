"""Area calculations from masks and pixel resolution."""
from typing import Any, Optional
import numpy as np


def pixel_area_km2(resolution_m: float) -> float:
    return (resolution_m * resolution_m) / 1_000_000.0


def mask_area_km2(mask: np.ndarray, resolution_m: float) -> float:
    """mask: boolean array True = feature of interest."""
    count = int(np.sum(mask))
    return round(count * pixel_area_km2(resolution_m), 4)


def aoi_area_from_bbox(bbox: list, resolution_m: float = None) -> float:
    """Approximate geodesic-ish area from bbox (degrees)."""
    min_lon, min_lat, max_lon, max_lat = bbox
    import math
    lat_span = max_lat - min_lat
    lon_span = max_lon - min_lon
    mid_lat = (min_lat + max_lat) / 2
    km_per_lon = 111.0 * math.cos(math.radians(mid_lat))
    return round(abs(lat_span * 111.0 * lon_span * km_per_lon), 2)


def aoi_area_from_geojson(aoi: dict[str, Any]) -> float:
    """Approximate a GeoJSON polygon area in square kilometres."""
    from pyproj import Geod
    from shapely.geometry import shape

    polygon = shape(aoi)
    geod = Geod(ellps="WGS84")
    area_m2, _ = geod.geometry_area_perimeter(polygon)
    return round(abs(area_m2) / 1_000_000.0, 6)
