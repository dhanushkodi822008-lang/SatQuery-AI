"""
Raster analysis orchestration: fetch real bands and compute NDVI/NDWI/NDBI.
Falls back to METADATA_ONLY only when band fetch fails — never invents percentages.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import numpy as np

from backend.processing.ndvi import compute_ndvi
from backend.processing.ndwi import compute_ndwi
from backend.processing.ndbi import compute_ndbi


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

    fetched = fetch_optical_bands(
        scene,
        bbox,
        needed=[band for band in ("green", "red", "nir", "swir16") if band in needed],
    )
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
        aoi_pixel_count = int(np.sum(inside))
        nodata_mask = ~inside
    else:
        inside = np.ones(tuple(results["shape"]), dtype=bool)
        aoi_pixel_count = int(inside.size)

    if aoi_pixel_count == 0:
        return {
            "success": False,
            "error": "The selected AOI does not overlap the satellite raster.",
            "mode": "NO_AOI_COVERAGE",
            "scene": _scene_summary(scene),
        }

    def measurement(mask: np.ndarray, valid: np.ndarray) -> Dict[str, Any]:
        valid_aoi = valid & inside
        detected = mask & valid_aoi
        detected_count = int(np.sum(detected))
        valid_count = int(np.sum(valid_aoi))
        percent_of_aoi = detected_count / aoi_pixel_count * 100.0
        valid_coverage = valid_count / aoi_pixel_count * 100.0
        area_km2 = aoi_area_km2 * percent_of_aoi / 100.0
        return {
            "pixel_count": detected_count,
            "valid_pixel_count": valid_count,
            "valid_coverage_pct": round(valid_coverage, 2),
            "fraction": detected_count / valid_count if valid_count else 0.0,
            "pct_approx": round(percent_of_aoi, 2),
            "pct_of_aoi": round(percent_of_aoi, 2),
            "area_km2": round(area_km2, 4),
            "area_ha": round(area_km2 * 100.0, 4),
        }

    # NDWI water
    if ("ndwi" in analyses or "water" in analyses) and "green" in bands and "nir" in bands:
        ndwi = compute_ndwi(bands["green"], bands["nir"], nodata_mask=nodata_mask, water_threshold=0.0)
        water_mask = ndwi.pop("water_mask", None)
        ndwi.pop("array", None)
        if ndwi.get("success") and water_mask is not None:
            valid = np.isfinite(bands["green"]) & np.isfinite(bands["nir"]) & ~nodata_mask
            measured = measurement(water_mask, valid)
            results["indices"]["ndwi"] = ndwi
            results["quantitative_result"]["water"] = {
                **measured,
                "fraction_of_valid_pixels": measured["fraction"],
                "pct_of_aoi_approx": measured["pct_of_aoi"],
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
            valid_mask = np.isfinite(veg_array) & inside
            # Agriculture: Moderate NDVI (0.18 < NDVI <= 0.45)
            agri_mask = valid_mask & (veg_array > 0.18) & (veg_array <= 0.45)
            agri = measurement(agri_mask, valid_mask)
            results["quantitative_result"]["agriculture"] = {
                **agri,
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
            forest_mask = valid_mask & (veg_array > 0.45)
            forest = measurement(forest_mask, valid_mask)
            results["quantitative_result"]["forest"] = {
                **forest,
                "mean_ndvi": ndvi.get("mean"),
                "method": "NDVI Dense Canopy Classification (NDVI > 0.45)",
                "note": "Closed forest canopy, dense woodland, plantations, and thick tree cover.",
                "observation_date": scene.get("acquisition_date"),
                "satellite": scene.get("satellite"),
            }
            results["map_geojson"]["forest"] = mask_to_geojson(forest_mask, bbox)

            # Combined vegetation for backwards compatibility
            veg_mask = valid_mask & (veg_array > 0.20)
            veg = measurement(veg_mask, valid_mask)
            results["quantitative_result"]["vegetation_indicated"] = {
                **veg,
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
        if ndbi.get("success") and built_mask is not None:
            results["indices"]["ndbi"] = ndbi
            valid = np.isfinite(bands["swir16"]) & np.isfinite(bands["nir"]) & ~nodata_mask
            built = measurement(built_mask, valid)
            results["quantitative_result"]["builtup_indicated"] = {
                **built,
                "method": ndbi.get("method"),
                "note": ndbi.get("note"),
                "observation_date": scene.get("acquisition_date"),
                "satellite": scene.get("satellite"),
            }
            results["quantitative_result"]["builtup"] = results["quantitative_result"]["builtup_indicated"]
            results["map_points"]["builtup"] = mask_to_geojson_points(built_mask, bbox)
            results["map_geojson"] = results.get("map_geojson", {})
            results["map_geojson"]["builtup"] = mask_to_geojson(built_mask, bbox)

    if not results["quantitative_result"]:
        results["message"] = "Bands fetched but index computation produced no quantitative result"
    else:
        results["message"] = "Real spectral indices computed from Planetary Computer COG bands over AOI"

    return results
