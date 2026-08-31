"""
NDVI computation from optical bands.
NDVI = (NIR - Red) / (NIR + Red)
Sentinel-2: B08 (NIR), B04 (Red)
Landsat-8/9: B5 (NIR), B4 (Red)
"""
from typing import Any, Dict, Optional
import numpy as np


def compute_ndvi(nir: np.ndarray, red: np.ndarray, nodata_mask: Optional[np.ndarray] = None) -> Dict[str, Any]:
    """
    Compute NDVI array and summary statistics from real band arrays.
    Requires actual reflectance arrays; does not invent values.
    """
    nir = np.asarray(nir, dtype=np.float32)
    red = np.asarray(red, dtype=np.float32)
    denom = nir + red
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = np.where(denom != 0, (nir - red) / denom, np.nan)
    if nodata_mask is not None:
        ndvi = np.where(nodata_mask, np.nan, ndvi)

    valid = ndvi[~np.isnan(ndvi)]
    if valid.size == 0:
        return {
            "success": False,
            "error": "No valid pixels for NDVI",
            "method": "NDVI = (NIR - Red) / (NIR + Red)",
        }

    # Vegetation indication (NDVI > 0.3 often used as rough threshold; not a land-cover class)
    veg_mask = valid > 0.3
    return {
        "success": True,
        "method": "NDVI = (NIR - Red) / (NIR + Red)",
        "index": "NDVI",
        "mean": float(np.nanmean(valid)),
        "median": float(np.nanmedian(valid)),
        "min": float(np.nanmin(valid)),
        "max": float(np.nanmax(valid)),
        "std": float(np.nanstd(valid)),
        "valid_pixel_count": int(valid.size),
        "vegetation_indicated_fraction": float(np.mean(veg_mask)),
        "note": (
            "NDVI indicates relative green vegetation vigor. "
            "It is NOT a direct classifier of agricultural land use. "
            "High NDVI can include forests, plantations, and crops."
        ),
        "array": ndvi,  # caller may drop this for JSON
    }
