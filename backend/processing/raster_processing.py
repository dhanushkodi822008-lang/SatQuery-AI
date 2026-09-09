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
    if ("ndwi" in analyses or "water" in analyses) and "green" in bands and "nir" in bands:
        ndwi = compute_ndwi(bands["green"], bands["nir"], nodata_mask=nodata_mask, water_threshold=0.0)
        water_mask = ndwi.pop("water_mask", None)
        ndwi.pop("array", None)
        if ndwi.get("success") and water_mask is not None:
            frac = float(ndwi.get("water_pixel_fraction") or 0.0)
            water_km2 = round(frac * aoi_area_km2, 4) if aoi_area_km2 > 0 else mask_area_km2(water_mask, res_m)
            results["indices"]["ndwi"] = ndwi
            results["quantitative_result"]["water"] = {
                "area_km2": water_km2,
                "fraction": frac,
                "fraction_of_valid_pixels": frac,
                "pct_approx": round(frac * 100, 2),
                "pct_of_aoi_approx": round(frac * 100, 2),
                "unit": "km²",
                "method": ndwi.get("method"),
                "observation_date": scene.get("acquisition_date"),
                "satellite": scene.get("satellite"),
                "sensor": scene.get("sensor"),
                "resolution_m": res_m,
            }
            results["map_points"]["water"] = mask_to_geojson_points(water_mask, bbox)
            results["map_geojson"] = results.get("map_geojson", {})
            results["map_geojson"]["water"] = mask_to_geojson(water_mask, bbox)

    # NDVI vegetation (Agriculture & Forest classification)
    if ("ndvi" in analyses or "agriculture" in analyses or "forest" in analyses) and "red" in bands and "nir" in bands:
        ndvi = compute_ndvi(bands["nir"], bands["red"], nodata_mask=nodata_mask)
        veg_array = ndvi.get("array")
        ndvi.pop("array", None)
        if ndvi.get("success") and veg_array is not None:
            results["indices"]["ndvi"] = ndvi
            valid_pixels = np.sum(np.isfinite(veg_array))
            total_valid = max(1, int(valid_pixels))

            # Agriculture: Moderate NDVI (0.18 < NDVI <= 0.45)
            agri_mask = np.isfinite(veg_array) & (veg_array > 0.18) & (veg_array <= 0.45)
            agri_frac = float(np.sum(agri_mask) / total_valid)
            agri_km2 = round(agri_frac * aoi_area_km2, 4) if aoi_area_km2 > 0 else mask_area_km2(agri_mask, res_m)
            results["quantitative_result"]["agriculture"] = {
                "area_km2": agri_km2,
                "fraction": agri_frac,
                "pct_approx": round(agri_frac * 100, 2),
                "mean_ndvi": ndvi.get("mean"),
                "method": "NDVI Agricultural Classification (0.18 < NDVI <= 0.45)",
                "note": "Agricultural cropland, cultivated fields, pasture, and open vegetative cover.",
                "observation_date": scene.get("acquisition_date"),
                "satellite": scene.get("satellite"),
            }
            results["map_geojson"] = results.get("map_geojson", {})
            results["map_geojson"]["agriculture"] = mask_to_geojson(agri_mask, bbox)
            results["map_geojson"]["vegetation"] = results["map_geojson"]["agriculture"]

            # Forest & Canopy: High NDVI (> 0.45)
            forest_mask = np.isfinite(veg_array) & (veg_array > 0.45)
            forest_frac = float(np.sum(forest_mask) / total_valid)
            forest_km2 = round(forest_frac * aoi_area_km2, 4) if aoi_area_km2 > 0 else mask_area_km2(forest_mask, res_m)
            results["quantitative_result"]["forest"] = {
                "area_km2": forest_km2,
                "fraction": forest_frac,
                "pct_approx": round(forest_frac * 100, 2),
                "mean_ndvi": ndvi.get("mean"),
                "method": "NDVI Dense Canopy Classification (NDVI > 0.45)",
                "note": "Closed forest canopy, dense woodland, plantations, and thick tree cover.",
                "observation_date": scene.get("acquisition_date"),
                "satellite": scene.get("satellite"),
            }
            results["map_geojson"]["forest"] = mask_to_geojson(forest_mask, bbox)

            # Combined vegetation for backwards compatibility
            veg_mask = np.isfinite(veg_array) & (veg_array > 0.20)
            veg_frac = float(np.sum(veg_mask) / total_valid)
            results["quantitative_result"]["vegetation_indicated"] = {
                "area_km2": round(veg_frac * aoi_area_km2, 4) if aoi_area_km2 > 0 else mask_area_km2(veg_mask, res_m),
                "fraction": veg_frac,
                "pct_approx": round(veg_frac * 100, 2),
                "mean_ndvi": ndvi.get("mean"),
                "method": ndvi.get("method"),
                "observation_date": scene.get("acquisition_date"),
                "satellite": scene.get("satellite"),
            }

    # NDBI built-up indication
    if ("ndbi" in analyses or "builtup" in analyses) and "swir16" in bands and "nir" in bands:
        ndbi = compute_ndbi(bands["swir16"], bands["nir"], nodata_mask=nodata_mask, builtup_threshold=0.0)
        built_mask = ndbi.pop("builtup_mask", None)
        ndbi.pop("array", None)
        if ndbi.get("success"):
            results["indices"]["ndbi"] = ndbi
            bfrac = float(ndbi.get("builtup_indicated_fraction") or 0.0)
            built_km2 = round(bfrac * aoi_area_km2, 4) if aoi_area_km2 > 0 else (mask_area_km2(built_mask, res_m) if built_mask is not None else 0.0)
            results["quantitative_result"]["builtup_indicated"] = {
                "area_km2": built_km2,
                "fraction": bfrac,
                "pct_approx": round(bfrac * 100, 2),
                "method": ndbi.get("method"),
                "note": ndbi.get("note"),
                "observation_date": scene.get("acquisition_date"),
                "satellite": scene.get("satellite"),
            }
            results["quantitative_result"]["builtup"] = results["quantitative_result"]["builtup_indicated"]
            if built_mask is not None:
                results["map_points"]["builtup"] = mask_to_geojson_points(built_mask, bbox)
                results["map_geojson"] = results.get("map_geojson", {})
                results["map_geojson"]["builtup"] = mask_to_geojson(built_mask, bbox)

    if not results["quantitative_result"]:
        results["message"] = "Bands fetched but index computation produced no quantitative result"
    else:
        results["message"] = "Real spectral indices computed from Planetary Computer COG bands over AOI"

    return results
