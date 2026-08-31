"""Input validation helpers."""
from typing import Any, Dict, Tuple, Optional
from pydantic import BaseModel, Field, field_validator
import re


def validate_polygon_geojson(value: Any) -> Dict[str, Any]:
    """Validate a GeoJSON Polygon and return its normalized mapping."""
    if not isinstance(value, dict) or value.get("type") != "Polygon":
        raise ValueError("AOI must be a GeoJSON Polygon.")
    coordinates = value.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        raise ValueError("AOI polygon coordinates are empty.")
    try:
        from shapely.geometry import shape
        polygon = shape(value)
    except Exception as exc:
        raise ValueError("AOI polygon coordinates are invalid.") from exc
    if polygon.is_empty:
        raise ValueError("AOI polygon is empty.")
    if not polygon.is_valid:
        raise ValueError("AOI polygon is invalid or self-intersecting.")
    if polygon.geom_type != "Polygon":
        raise ValueError("AOI must contain exactly one Polygon geometry.")
    for lon, lat in polygon.exterior.coords:
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError("AOI coordinates must be longitude/latitude values.")
    return value


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
        # 1 deg lat ≈ 111 km; lon varies with cos(lat)
        mid_lat = (self.min_lat + self.max_lat) / 2
        import math
        km_per_lon = 111.0 * math.cos(math.radians(mid_lat))
        return abs(lat_span * 111.0 * lon_span * km_per_lon)


def parse_coordinates(text: str) -> Optional[Tuple[float, float]]:
    """Parse 'lat, lon' or 'lat lon' strings."""
    text = text.strip()
    # Match decimal degrees
    m = re.match(
        r"^([+-]?\d+\.?\d*)\s*[, ]\s*([+-]?\d+\.?\d*)$",
        text,
    )
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
    return None


def sanitize_query(query: str, max_len: int = 500) -> str:
    q = (query or "").strip()
    if len(q) > max_len:
        q = q[:max_len]
    # Remove control characters
    q = re.sub(r"[\x00-\x1f\x7f]", "", q)
    return q
