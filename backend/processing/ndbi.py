"""
NDBI for built-up indication.
NDBI = (SWIR - NIR) / (SWIR + NIR)
Sentinel-2: B11 (SWIR), B08 (NIR)
"""
from typing import Any, Dict, Optional
import numpy as np


def compute_ndbi(swir: np.ndarray, nir: np.ndarray, nodata_mask: Optional[np.ndarray] = None,
                 builtup_threshold: float = 0.0) -> Dict[str, Any]:
    swir = np.asarray(swir, dtype=np.float32)
    nir = np.asarray(nir, dtype=np.float32)
    denom = swir + nir
    with np.errstate(divide="ignore", invalid="ignore"):
        ndbi = np.where(denom != 0, (swir - nir) / denom, np.nan)
    if nodata_mask is not None:
        ndbi = np.where(nodata_mask, np.nan, ndbi)

    valid = ndbi[~np.isnan(ndbi)]
    if valid.size == 0:
        return {
            "success": False,
            "error": "No valid pixels for NDBI",
            "method": "NDBI = (SWIR - NIR) / (SWIR + NIR)",
        }

    built_mask = (ndbi > builtup_threshold) & ~np.isnan(ndbi)
    built_fraction = float(np.nansum(built_mask) / max(1, np.sum(~np.isnan(ndbi))))

    return {
        "success": True,
        "method": "NDBI = (SWIR - NIR) / (SWIR + NIR)",
        "index": "NDBI",
        "threshold": builtup_threshold,
        "mean": float(np.nanmean(valid)),
        "median": float(np.nanmedian(valid)),
        "builtup_indicated_fraction": built_fraction,
        "valid_pixel_count": int(valid.size),
        "note": (
            "NDBI is an indication of built-up / bare soil spectral response. "
            "It is not a perfect building detector; bright dry soil can also elevate NDBI."
        ),
        "array": ndbi,
        "builtup_mask": built_mask,
    }
