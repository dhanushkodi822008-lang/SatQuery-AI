"""
Raster analysis orchestration: fetch real bands and compute NDVI/NDWI/NDBI.
Falls back to METADATA_ONLY only when band fetch fails — never invents percentages.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import numpy as np

from backend.utils.logging import logger
from backend.processing.ndvi import compute_ndvi
from backend.processing.ndwi import compute_ndwi
from backend.processing.ndbi import compute_ndbi
from backend.processing.area_calculation import mask_area_km2, aoi_area_from_bbox


def summarize_without_raster(
    scene: Dict[str, Any],
    aoi_area_km2: float,
    analysis_type: str,
) -> Dict[str, Any]:
    return {
        "success": True,
        "mode": "METADATA_ONLY",
        "message": (
            "Scene metadata retrieved from catalog. "
            "Full band raster could not be processed in this run. "
            "No water/agriculture/built-up percentages are fabricated."
        ),
        "analysis_type": analysis_type,
        "scene": _scene_summary(scene),
        "aoi_area_km2": aoi_area_km2,
        "quantitative_result": None,
    }


def _scene_summary(scene: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": scene.get("id"),
        "satellite": scene.get("satellite"),
        "sensor": scene.get("sensor"),
        "acquisition_date": scene.get("acquisition_date"),
        "cloud_cover_pct": scene.get("cloud_cover_pct"),
        "resolution_m": scene.get("resolution_m"),
        "collection": scene.get("collection"),
        "processing_level": scene.get("processing_level"),
    }


def analyze_optical_aoi(
    scene: Dict[str, Any],
    bbox: List[float],
    aoi_area_km2: float,
    analyses: Optional[List[str]] = None,
    aoi_geojson: Optional[Dict[str, Any]] = None,
    vegetation_threshold: float = 0.3,
) -> Dict[str, Any]:
    """
    Fetch real bands and compute requested indices over AOI.
    analyses: subset of ['ndwi','ndvi','ndbi']
    """
    if analyses is None:
        analyses = ["ndwi", "ndvi", "ndbi"]

    from backend.services.raster_fetch_service import fetch_optical_bands, mask_to_geojson, mask_to_geojson_points

    needed = set()
    if "ndwi" in analyses:
        needed.update(["green", "nir"])
    if "ndvi" in analyses:
        needed.update(["red", "nir"])
    if "ndbi" in analyses:
        needed.update(["swir16", "nir"])

    fetched = fetch_optical_bands(scene, bbox, needed=list(needed))
    if not fetched.get("success"):
        meta = summarize_without_raster(scene, aoi_area_km2, ",".join(analyses))
        meta["fetch_error"] = fetched.get("error")
        meta["fetch_mode"] = fetched.get("mode")
        meta["fetch_details"] = {
            "missing": fetched.get("missing", []),
            "signing_error": fetched.get("signing_error"),
            "read_errors": fetched.get("read_errors", []),
            "asset_details": fetched.get("asset_details", []),
        }
        return meta

    bands = fetched["bands"]
    res_m = float(fetched.get("resolution_m") or 10)
    results: Dict[str, Any] = {
        "success": True,
        "mode": "RASTER",
        "scene": _scene_summary(scene),
        "aoi_area_km2": aoi_area_km2,
        "shape": fetched.get("shape"),
        "resolution_m": res_m,
        "missing_bands": fetched.get("missing"),
        "source": "Microsoft Planetary Computer (signed COG windowed read)",
        "indices": {},
        "map_points": {},
        "map_geojson": {},
        "quantitative_result": {},
        "analysis_area": "manual polygon" if aoi_geojson else "automatic location AOI",
    }

    nodata_mask = np.zeros(results["shape"], dtype=bool)
    if aoi_geojson:
        from rasterio.features import geometry_mask
        from rasterio.transform import from_bounds
        inside = geometry_mask(
            [aoi_geojson],
            out_shape=tuple(results["shape"]),
            transform=from_bounds(*bbox, results["shape"][1], results["shape"][0]),
            invert=True,
        )
        nodata_mask = ~inside

    # NDWI water
    if "ndwi" in analyses and "green" in bands and "nir" in bands:
        ndwi = compute_ndwi(bands["green"], bands["nir"], nodata_mask=nodata_mask, water_threshold=0.0)
        # Drop large arrays from JSON-serializable path
        water_mask = ndwi.pop("water_mask", None)
        ndwi.pop("array", None)
        if ndwi.get("success") and water_mask is not None:
            water_km2 = mask_area_km2(water_mask, res_m)
            frac = ndwi.get("water_pixel_fraction") or 0
            results["indices"]["ndwi"] = ndwi
            results["quantitative_result"]["water"] = {
                "area_km2": water_km2,
                "fraction_of_valid_pixels": frac,
                "pct_of_aoi_approx": round(frac * 100, 2),
                "unit": "km² (from valid pixels × resolution)",
                "method": ndwi.get("method"),
                "observation_date": scene.get("acquisition_date"),
                "satellite": scene.get("satellite"),
                "sensor": scene.get("sensor"),
                "resolution_m": res_m,
            }
            results["map_points"]["water"] = mask_to_geojson_points(water_mask, bbox)
            results["map_geojson"] = results.get("map_geojson", {})
            results["map_geojson"]["water"] = mask_to_geojson(water_mask, bbox)

    # NDVI vegetation
    if "ndvi" in analyses and "red" in bands and "nir" in bands:
        ndvi = compute_ndvi(bands["nir"], bands["red"], nodata_mask=nodata_mask)
        veg_array = ndvi.get("array")
        vegetation_mask = np.isfinite(veg_array) & (veg_array > vegetation_threshold) if veg_array is not None else None
        ndvi.pop("array", None)
        if ndvi.get("success"):
            results["indices"]["ndvi"] = ndvi
            veg_frac = ndvi.get("vegetation_indicated_fraction") or 0
            results["quantitative_result"]["vegetation_indicated"] = {
                "fraction": float(np.sum(vegetation_mask) / max(1, np.sum(np.isfinite(veg_array)))) if vegetation_mask is not None else veg_frac,
                "pct_approx": round((float(np.sum(vegetation_mask) / max(1, np.sum(np.isfinite(veg_array)))) if vegetation_mask is not None else veg_frac) * 100, 2),
                "mean_ndvi": ndvi.get("mean"),
                "method": ndvi.get("method"),
                "note": ndvi.get("note"),
                "observation_date": scene.get("acquisition_date"),
                "satellite": scene.get("satellite"),
            }
            if veg_array is not None:
                results["map_geojson"]["vegetation"] = mask_to_geojson(vegetation_mask, bbox)

    # NDBI built-up indication
    if "ndbi" in analyses and "swir16" in bands and "nir" in bands:
        ndbi = compute_ndbi(bands["swir16"], bands["nir"], nodata_mask=nodata_mask, builtup_threshold=0.0)
        built_mask = ndbi.pop("builtup_mask", None)
        ndbi.pop("array", None)
        if ndbi.get("success"):
            results["indices"]["ndbi"] = ndbi
            bfrac = ndbi.get("builtup_indicated_fraction") or 0
            results["quantitative_result"]["builtup_indicated"] = {
                "fraction": bfrac,
                "pct_approx": round(bfrac * 100, 2),
                "area_km2_approx": mask_area_km2(built_mask, res_m) if built_mask is not None else None,
                "method": ndbi.get("method"),
                "note": ndbi.get("note"),
                "observation_date": scene.get("acquisition_date"),
                "satellite": scene.get("satellite"),
            }
            if built_mask is not None:
                results["map_points"]["builtup"] = mask_to_geojson_points(built_mask, bbox)
                results["map_geojson"] = results.get("map_geojson", {})
                results["map_geojson"]["builtup"] = mask_to_geojson(built_mask, bbox)

    if not results["quantitative_result"]:
        results["message"] = "Bands fetched but index computation produced no quantitative result"
    else:
        results["message"] = "Real spectral indices computed from Planetary Computer COG bands over AOI"

    return results
