"""
Before/After change detection.

Rules:
- Geographic change detection requires valid CRS + compatible spatial alignment.
- Never present generic pixel variance as geographic/AOI change.
- Reproject/resample only when both images have CRS and a reliable common grid can be formed.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def get_image_path(image_id: str) -> Path:
    candidates = list(settings.UPLOADS_DIR.glob(f"{image_id}.*"))
    if not candidates:
        raise ValueError(f"Image not found for ID: {image_id}")
    return candidates[0]


def compare_images(image_before_id: str, image_after_id: str) -> Dict[str, Any]:
    path_before = get_image_path(image_before_id)
    path_after = get_image_path(image_after_id)

    ext_before = path_before.suffix.lower()
    ext_after = path_after.suffix.lower()

    is_geo_before = ext_before in {".tif", ".tiff"}
    is_geo_after = ext_after in {".tif", ".tiff"}

    if is_geo_before and is_geo_after:
        return _compare_geotiffs(path_before, path_after)

    # Non-georeferenced imagery: never claim geographic change
    return {
        "success": False,
        "error": (
            "Images lack geospatial metadata (CRS/georeferencing). "
            "Generic pixel comparison is not reported as geographic change detection. "
            "Upload georeferenced GeoTIFFs with compatible CRS and overlapping extent."
        ),
        "method": None,
        "geographic_change": False,
    }


def _read_geotiff_meta(path: Path) -> Dict[str, Any]:
    import rasterio

    with rasterio.open(path) as src:
        return {
            "crs": src.crs,
            "bounds": src.bounds,
            "transform": src.transform,
            "width": src.width,
            "height": src.height,
            "count": src.count,
            "dtype": str(src.dtypes[0]) if src.count else None,
            "res": src.res,
        }


def _arrays_aligned(
    path_before: Path, path_after: Path
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[str], Optional[Dict]]:
    """
    Return aligned float32 band-1 arrays on a common grid, or (None, None, error, meta).
    Attempts safe reprojection when CRS differs but both are defined.
    """
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject, calculate_default_transform
    from rasterio.transform import array_bounds

    with rasterio.open(path_before) as src_b, rasterio.open(path_after) as src_a:
        if src_b.crs is None or src_a.crs is None:
            return None, None, (
                "CRS is missing on one or both GeoTIFFs. "
                "Spatial map and geospatial change analysis require georeferencing."
            ), None

        # Same CRS, same shape, same transform → direct compare
        same_crs = src_b.crs == src_a.crs
        same_shape = src_b.shape == src_a.shape
        same_transform = src_b.transform == src_a.transform

        if same_crs and same_shape and same_transform:
            b = src_b.read(1).astype(np.float32)
            a = src_a.read(1).astype(np.float32)
            meta = {
                "crs": str(src_b.crs),
                "width": src_b.width,
                "height": src_b.height,
                "transform": list(src_b.transform)[:6],
                "bounds": list(src_b.bounds),
                "alignment": "exact_match",
            }
            return b, a, None, meta

        # Same CRS, overlapping bounds → resample "after" onto "before" grid
        if same_crs:
            # Check overlap
            b_bounds = src_b.bounds
            a_bounds = src_a.bounds
            overlap = not (
                a_bounds.right < b_bounds.left
                or a_bounds.left > b_bounds.right
                or a_bounds.top < b_bounds.bottom
                or a_bounds.bottom > b_bounds.top
            )
            if not overlap:
                return None, None, (
                    "Images share CRS but spatial extents do not overlap. "
                    "Cannot perform geographic change detection."
                ), None

            dest = np.zeros(src_b.shape, dtype=np.float32)
            reproject(
                source=rasterio.band(src_a, 1),
                destination=dest,
                src_transform=src_a.transform,
                src_crs=src_a.crs,
                dst_transform=src_b.transform,
                dst_crs=src_b.crs,
                resampling=Resampling.bilinear,
            )
            b = src_b.read(1).astype(np.float32)
            meta = {
                "crs": str(src_b.crs),
                "width": src_b.width,
                "height": src_b.height,
                "transform": list(src_b.transform)[:6],
                "bounds": list(src_b.bounds),
                "alignment": "resampled_same_crs",
            }
            return b, dest, None, meta

        # Different CRS — reproject after onto before's CRS/grid (conservative)
        try:
            dst_crs = src_b.crs
            transform, width, height = calculate_default_transform(
                src_a.crs,
                dst_crs,
                src_a.width,
                src_a.height,
                *src_a.bounds,
            )
            # Use before's grid when possible if reprojected after roughly matches
            # Prefer before grid for consistency
            dest = np.zeros(src_b.shape, dtype=np.float32)
            reproject(
                source=rasterio.band(src_a, 1),
                destination=dest,
                src_transform=src_a.transform,
                src_crs=src_a.crs,
                dst_transform=src_b.transform,
                dst_crs=src_b.crs,
                resampling=Resampling.bilinear,
            )
            # Sanity: reject if almost all zeros (no real overlap after reproject)
            if np.count_nonzero(dest) < max(100, 0.01 * dest.size):
                return None, None, (
                    f"CRS mismatch ({src_b.crs} vs {src_a.crs}). "
                    "After reprojection, spatial overlap is insufficient for reliable change detection."
                ), None
            b = src_b.read(1).astype(np.float32)
            meta = {
                "crs": str(src_b.crs),
                "width": src_b.width,
                "height": src_b.height,
                "transform": list(src_b.transform)[:6],
                "bounds": list(src_b.bounds),
                "alignment": "reprojected",
                "source_crs_before": str(src_b.crs),
                "source_crs_after": str(src_a.crs),
            }
            return b, dest, None, meta
        except Exception as e:
            return None, None, (
                f"CRS mismatch ({src_b.crs} vs {src_a.crs}). "
                f"Reliable reprojection failed: {type(e).__name__}: {e}. "
                "Reproject/resample both images to a common grid offline, then retry."
            ), None


def _compare_geotiffs(path_before: Path, path_after: Path) -> Dict[str, Any]:
    before, after, err, meta = _arrays_aligned(path_before, path_after)
    if err or before is None or after is None:
        return {
            "success": False,
            "error": err or "Alignment failed",
            "geographic_change": False,
            "method": None,
        }

    # Valid-pixel mask: ignore nodata-ish zeros if both are zero
    valid = ~((before == 0) & (after == 0))
    if np.count_nonzero(valid) < 50:
        return {
            "success": False,
            "error": "Too few valid overlapping pixels after alignment.",
            "geographic_change": False,
        }

    diff = after.astype(np.float32) - before.astype(np.float32)
    abs_diff = np.abs(diff)
    # Threshold: robust to outliers — use median absolute deviation style
    med = float(np.median(abs_diff[valid]))
    mad = float(np.median(np.abs(abs_diff[valid] - med))) if np.any(valid) else 0.0
    thresh = max(med + 3.0 * (1.4826 * mad if mad > 0 else 0), 1e-3)
    changed = (abs_diff > thresh) & valid
    changed_pixels = int(np.count_nonzero(changed))
    valid_pixels = int(np.count_nonzero(valid))
    pct_change = (changed_pixels / valid_pixels) * 100.0 if valid_pixels else 0.0

    # Approximate area if transform available (pixel size)
    area_km2 = None
    try:
        if meta and meta.get("transform"):
            # transform: a, b, c, d, e, f — |a| and |e| are pixel sizes in CRS units
            px_w = abs(float(meta["transform"][0]))
            px_h = abs(float(meta["transform"][4]))
            # Assume geographic or projected; if degrees, skip area
            if meta.get("crs") and "4326" not in str(meta["crs"]):
                area_km2 = round((changed_pixels * px_w * px_h) / 1e6, 4)
    except Exception:
        area_km2 = None

    return {
        "success": True,
        "geographic_change": True,
        "method": "GeoTIFF geospatial change detection (aligned)",
        "crs": meta.get("crs") if meta else None,
        "alignment": meta.get("alignment") if meta else None,
        "stats": {
            "valid_pixels": valid_pixels,
            "changed_pixels": changed_pixels,
            "percentage_changed": round(pct_change, 2),
            "changed_area_km2": area_km2,
            "change_threshold": round(thresh, 6),
        },
        "report_summary": (
            f"Aligned geospatial comparison: {round(pct_change, 2)}% of valid pixels changed "
            f"({changed_pixels}/{valid_pixels}). "
            + (f"Approx. changed area {area_km2} km². " if area_km2 is not None else "")
            + "This is a spectral/pixel-difference indicator on a common grid, not a certified land-cover change product."
        ),
        "meta": meta,
    }
