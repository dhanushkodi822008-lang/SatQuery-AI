"""Input validation helpers."""
from typing import Any, Dict, Tuple, Optional
from pydantic import BaseModel, Field, field_validator
import re


def validate_polygon_geojson(value: Any) -> Dict[str, Any]:
    """Validate a GeoJSON Polygon or MultiPolygon and return its normalized mapping."""
    if not isinstance(value, dict):
        raise ValueError("AOI must be a GeoJSON object (dict).")
    
    geom = value
    if value.get("type") == "Feature":
        geom = value.get("geometry") or {}
    elif value.get("type") == "FeatureCollection":
        feats = value.get("features") or []
        if not feats:
            raise ValueError("AOI FeatureCollection contains no features.")
        geom = (feats[0].get("geometry") if isinstance(feats[0], dict) else None) or {}
        
    gtype = geom.get("type")
    if gtype not in ("Polygon", "MultiPolygon"):
        raise ValueError("AOI geometry must be a GeoJSON Polygon or MultiPolygon.")
        
    coordinates = geom.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        raise ValueError("AOI geometry coordinates are empty.")
        
    try:
        from shapely.geometry import shape
        poly = shape(geom)
    except Exception as exc:
        raise ValueError("AOI geometry coordinates are invalid.") from exc
        
    if poly.is_empty:
        raise ValueError("AOI geometry is empty.")
    if not poly.is_valid:
        # Attempt to fix self-intersections gracefully if possible
        try:
            poly = poly.buffer(0)
        except Exception:
            raise ValueError("AOI geometry is invalid or self-intersecting.")
            
    # Validate bounds
    bounds = poly.bounds
    if not (-180 <= bounds[0] <= 180 and -90 <= bounds[1] <= 90 and -180 <= bounds[2] <= 180 and -90 <= bounds[3] <= 90):
        raise ValueError("AOI coordinates must be in standard WGS84 longitude/latitude bounds.")
        
    return geom


class Coordinate(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class AOI(BaseModel):
    min_lat: float = Field(..., ge=-90, le=90)
    min_lon: float = Field(..., ge=-180, le=180)
    max_lat: float = Field(..., ge=-90, le=90)
    max_lon: float = Field(..., ge=-180, le=180)

    @field_validator("max_lat")
    @classmethod
    def check_lat_order(cls, v, info):
        if "min_lat" in info.data and v < info.data["min_lat"]:
            raise ValueError("max_lat must be >= min_lat")
        return v

    @field_validator("max_lon")
    @classmethod
    def check_lon_order(cls, v, info):
        if "min_lon" in info.data and v < info.data["min_lon"]:
            raise ValueError("max_lon must be >= min_lon")
        return v

    def bbox(self) -> list[float]:
        return [self.min_lon, self.min_lat, self.max_lon, self.max_lat]

    def area_approx_km2(self) -> float:
        """Rough area estimate (not geodesic)."""
        lat_span = self.max_lat - self.min_lat
        lon_span = self.max_lon - self.min_lon
        mid_lat = (self.min_lat + self.max_lat) / 2
        import math
        km_per_lon = 111.0 * math.cos(math.radians(mid_lat))
        return abs(lat_span * 111.0 * lon_span * km_per_lon)


def parse_coordinates(text: str) -> Optional[Tuple[float, float]]:
    """Parse lat/lon coordinates from various string formats."""
    if not text:
        return None
    raw = text.strip()

    # 1. "lat: 11.2189, lon: 78.1674" or "latitude 11.2189 longitude 78.1674"
    named_match = re.search(
        r"(?:lat(?:itude)?[:\s=]+)([+-]?\d+\.?\d*)[,\s]+(?:lon(?:gitude)?|lng)[:\s=]+([+-]?\d+\.?\d*)",
        raw,
        re.IGNORECASE,
    )
    if named_match:
        try:
            lat = float(named_match.group(1))
            lon = float(named_match.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
        except ValueError:
            pass

    # 2. "11.2189N, 78.1674E" or "11.2189 S, 78.1674 W"
    cardinal_match = re.search(
        r"([+-]?\d+\.?\d*)\s*([NSns])[,\s]+([+-]?\d+\.?\d*)\s*([EWew])",
        raw,
    )
    if cardinal_match:
        try:
            lat = float(cardinal_match.group(1)) * (-1 if cardinal_match.group(2).upper() == "S" else 1)
            lon = float(cardinal_match.group(3)) * (-1 if cardinal_match.group(4).upper() == "W" else 1)
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
        except ValueError:
            pass

    # 3. Standard decimal pair: "11.2189, 78.1674" or "11.2189 78.1674"
    pair_matches = re.findall(
        r"([+-]?\d{1,3}(?:\.\d+)?)\s*[, ]\s*([+-]?\d{1,3}(?:\.\d+)?)",
        raw,
    )
    for lat_str, lon_str in pair_matches:
        try:
            lat = float(lat_str)
            lon = float(lon_str)
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
        except ValueError:
            continue

    return None


def sanitize_query(query: str, max_len: int = 500) -> str:
    q = (query or "").strip()
    if len(q) > max_len:
        q = q[:max_len]
    q = re.sub(r"[\x00-\x1f\x7f]", "", q)
    return q
