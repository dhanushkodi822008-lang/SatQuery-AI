"""
NDWI (McFeeters) for water detection.
NDWI = (Green - NIR) / (Green + NIR)
Sentinel-2: B03 (Green), B08 (NIR)
"""
from typing import Any, Dict, Optional
import numpy as np


def compute_ndwi(green: np.ndarray, nir: np.ndarray, nodata_mask: Optional[np.ndarray] = None,
                 water_threshold: float = 0.0) -> Dict[str, Any]:
    """
    Compute NDWI and water mask from real band arrays.
    """
    green = np.asarray(green, dtype=np.float32)
    nir = np.asarray(nir, dtype=np.float32)
    denom = green + nir
    with np.errstate(divide="ignore", invalid="ignore"):
        ndwi = np.where(denom != 0, (green - nir) / denom, np.nan)
    if nodata_mask is not None:
        ndwi = np.where(nodata_mask, np.nan, ndwi)

    valid = ndwi[~np.isnan(ndwi)]
    if valid.size == 0:
        return {
            "success": False,
            "error": "No valid pixels for NDWI",
            "method": "NDWI (McFeeters) = (Green - NIR) / (Green + NIR)",
        }

    water_mask = (ndwi > water_threshold) & ~np.isnan(ndwi)
    water_fraction = float(np.nansum(water_mask) / max(1, np.sum(~np.isnan(ndwi))))

    return {
        "success": True,
        "method": "NDWI (McFeeters) = (Green - NIR) / (Green + NIR)",
        "index": "NDWI",
        "threshold": water_threshold,
        "mean": float(np.nanmean(valid)),
        "median": float(np.nanmedian(valid)),
        "min": float(np.nanmin(valid)),
        "max": float(np.nanmax(valid)),
        "water_pixel_fraction": water_fraction,
        "valid_pixel_count": int(valid.size),
        "note": (
            "Water extent is a satellite-derived area estimate from spectral indices. "
            "It is NOT a gauge-measured water level in metres."
        ),
        "array": ndwi,
        "water_mask": water_mask,
    }
