"""
Visual grounding for SatQuery AI.
Produces pixel masks via spectral thresholding (water / vegetation / built-up),
vectorises to GeoJSON polygons in EPSG:4326, returns area and confidence.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from backend.ai.model_registry import get_registry
from backend.config import get_settings
from backend.utils.logging import logger

try:
    import rasterio
    from rasterio import features
    from rasterio.enums import Resampling
    from rasterio.warp import transform_geom
    from shapely.geometry import shape, mapping
    from shapely.ops import unary_union
except ImportError:
    rasterio = None  # type: ignore


THRESHOLDS = {
    "water": {"index": "ndwi", "min": 0.15, "description": "McFeeters-style NDWI > 0.15"},
    "vegetation": {"index": "ndvi", "min": 0.25, "description": "NDVI > 0.25"},
    "cropland": {"index": "ndvi", "min": 0.30, "max": 0.75, "description": "0.30 < NDVI < 0.75 (proxy)"},
    "builtup": {"index": "ndbi", "min": 0.05, "description": "NDBI > 0.05"},
}


def _detect_target(query: str) -> str:
    q = (query or "").lower()
    if any(w in q for w in ("water", "lake", "river", "flood", "pond", "reservoir")):
        return "water"
    if any(w in q for w in ("crop", "farm", "agri", "cultivat")):
        return "cropland"
    if any(w in q for w in ("veget", "green", "forest", "ndvi", "plant")):
        return "vegetation"
    if any(w in q for w in ("built", "urban", "building", "settlement", "city")):
        return "builtup"
    return "water"


def _compute_index(data: np.ndarray, name: str) -> np.ndarray:
    if data.shape[0] < 2:
        return data[0]
    a, b = data[0].astype(np.float32), data[-1].astype(np.float32)
    denom = a + b
    denom = np.where(np.abs(denom) < 1e-6, np.nan, denom)
    if name == "ndwi":
        return (a - b) / denom
    if name == "ndbi":
        return (b - a) / denom
    return (b - a) / denom


def _mask_from_index(idx: np.ndarray, target: str) -> Tuple[np.ndarray, Dict[str, Any]]:
    cfg = THRESHOLDS[target]
    mask = np.isfinite(idx)
    if "min" in cfg:
        mask &= idx >= cfg["min"]
    if "max" in cfg:
        mask &= idx <= cfg["max"]
    try:
        from scipy import ndimage
        mask = ndimage.binary_opening(mask, iterations=1)
        mask = ndimage.binary_closing(mask, iterations=1)
    except Exception:
        pass
    info = {
        "threshold": cfg,
        "positive_pixels": int(mask.sum()),
        "total_pixels": int(mask.size),
    }
    return mask.astype(np.uint8), info


def _vectorise(mask, transform, src_crs, min_area_px: int = 20):
    shapes = list(features.shapes(mask, mask=mask.astype(bool), transform=transform))
    features_out = []
    geoms = []
    for geom, val in shapes:
        if int(val) != 1:
            continue
        g = shape(geom)
        if g.area < min_area_px:
            continue
        try:
            if src_crs and str(src_crs) not in ("EPSG:4326", "WGS84"):
                geom_wgs = transform_geom(src_crs, "EPSG:4326", geom)
            else:
                geom_wgs = geom
        except Exception:
            geom_wgs = geom
        g_wgs = shape(geom_wgs)
        geoms.append(g_wgs)
        features_out.append({
            "type": "Feature",
            "properties": {"class": "target"},
            "geometry": mapping(g_wgs),
        })

    total_area_km2 = 0.0
    if geoms:
        try:
            from pyproj import Geod
            geod = Geod(ellps="WGS84")
            union = unary_union(geoms)
            if union.geom_type == "Polygon":
                area_m2, _ = geod.geometry_area_perimeter(union)
                total_area_km2 = abs(area_m2) / 1e6
            elif union.geom_type == "MultiPolygon":
                s = 0.0
                for poly in union.geoms:
                    a, _ = geod.geometry_area_perimeter(poly)
                    s += abs(a)
                total_area_km2 = s / 1e6
        except Exception:
            total_area_km2 = 0.0
    return features_out, round(total_area_km2, 4)


def _bboxes(features_list, top_n: int = 5):
    boxes = []
    for f in features_list:
        g = shape(f["geometry"])
        boxes.append(list(g.bounds))
    boxes.sort(key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
    return boxes[:top_n]


async def ground_phrase(query: str, context: Dict[str, Any]) -> Dict[str, Any]:
    model = get_registry()["grounding"]
    settings = get_settings()
    target = _detect_target(query)
    image_id = context.get("image_id")

    if rasterio is None:
        return {
            "success": False,
            "task": "grounding",
            "model": model.to_dict(),
            "query": query,
            "message": "rasterio not available for grounding.",
            "status": "ERROR",
        }

    path = None
    if image_id:
        candidates = list(settings.UPLOADS_DIR.glob(f"{image_id}.*"))
        if candidates:
            path = candidates[0]

    if path is None or not path.exists():
        return {
            "success": False,
            "task": "grounding",
            "model": model.to_dict(),
            "query": query,
            "target": target,
            "message": (
                "Grounding needs an uploaded GeoTIFF (image_id) for pixel masks. "
                "Upload a multi-band GeoTIFF, then ask 'show me where the water is'."
            ),
            "status": "NEED_IMAGE",
            "geojson": None,
            "area_km2": None,
        }

    try:
        with rasterio.open(path) as src:
            max_px = 1024
            scale = min(1.0, max_px / max(src.height, src.width))
            out_h = max(1, int(src.height * scale))
            out_w = max(1, int(src.width * scale))
            bands = min(src.count, 4)
            data = src.read(
                list(range(1, bands + 1)),
                out_shape=(bands, out_h, out_w),
                resampling=Resampling.bilinear,
            ).astype(np.float32)
            if src.nodata is not None:
                data = np.where(data == src.nodata, np.nan, data)

            transform = src.transform * src.transform.scale(
                (src.width / out_w), (src.height / out_h)
            )
            idx_name = THRESHOLDS[target]["index"]
            idx = _compute_index(data, idx_name)
            mask, mask_info = _mask_from_index(idx, target)
            feats, area_km2 = _vectorise(mask, transform, src.crs)
            boxes = _bboxes(feats)
            frac = mask_info["positive_pixels"] / max(1, mask_info["total_pixels"])
            conf = round(min(0.9, 0.4 + frac * 2), 2)

            return {
                "success": True,
                "task": "grounding",
                "model": model.to_dict(),
                "query": query,
                "target": target,
                "method": "spectral-threshold",
                "threshold": THRESHOLDS[target],
                "geojson": {"type": "FeatureCollection", "features": feats},
                "area_km2": area_km2,
                "bboxes": boxes,
                "confidence": conf,
                "pixel_stats": mask_info,
                "status": "READY",
                "certified": False,
                "note": "Spectral-baseline mask; not a deep open-vocabulary detector.",
            }
    except Exception as exc:
        logger.exception("grounding failed")
        return {
            "success": False,
            "task": "grounding",
            "model": model.to_dict(),
            "query": query,
            "message": str(exc),
            "status": "ERROR",
        }
