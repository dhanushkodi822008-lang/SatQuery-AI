import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from backend.config import get_settings
from backend.processing.raster_processing import analyze_optical_aoi
from backend.routes.image_routes import upload_image as upload_geotiff_route
from backend.services.landcover_service import LandCoverInputError, analyze_uploaded_landcover
from backend.services.satellite_service import get_best_optical_scene
from backend.utils.validation import validate_polygon_geojson

try:
    from shapely.geometry import shape
except Exception:  # pragma: no cover
    shape = None

router = APIRouter(prefix="/api/landcover", tags=["landcover"])
legacy_router = APIRouter(tags=["landcover"])
settings = get_settings()
_analysis_store: Dict[str, Dict[str, Any]] = {}
logger = logging.getLogger(__name__)


class LandCoverRequest(BaseModel):
    image_id: Optional[str] = Field(default=None, min_length=1, max_length=200)
    category: str = Field(..., min_length=1, max_length=80)
    aoi: Optional[Dict[str, Any]] = None
    location: Optional[Dict[str, Any]] = None
    bbox: Optional[List[float]] = None


def _resolve_uploaded_image(image_id: str) -> str:
    image_id = image_id.strip()
    if not image_id:
        raise HTTPException(status_code=400, detail="Missing uploaded image ID.")

    matches = sorted(
        path for path in settings.UPLOADS_DIR.iterdir()
        if path.is_file() and path.stem.lower() == image_id.lower()
    )
    image_path = matches[0] if matches else None
    if image_path is None or not image_path.is_file():
        raise HTTPException(status_code=404, detail="Uploaded image not found. Please upload a valid GeoTIFF first.")
    return str(image_path)


def _normalize_lc_class(category: str) -> str:
    normalized = category.strip()
    if normalized.lower() in {"overall", "overall measurement", "all"}:
        return "Overall Measurement"
    if normalized.lower() == "water":
        return "Water"
    if normalized.lower() in {"agriculture", "farm", "crops"}:
        return "Agriculture"
    if normalized.lower() in {"forest", "vegetation", "forest / vegetation", "forest/vegetation"}:
        return "Forest / Vegetation"
    if normalized.lower() in {"built-up", "builtup", "urban", "built up"}:
        return "Built-up"
    raise ValueError(f"Unsupported category '{category}'. Supported categories: Water, Agriculture, Forest / Vegetation, Built-up.")


def _bbox_from_request(aoi: Optional[Dict[str, Any]], location: Optional[Dict[str, Any]], bbox: Optional[List[float]]) -> List[float]:
    if aoi is not None:
        validate_polygon_geojson(aoi)
        if shape is None:
            raise ValueError("Shapely is required to process AOI geometry.")
        return list(shape(aoi).bounds)
    if bbox is not None and len(bbox) == 4:
        return [float(x) for x in bbox]
    if location is not None:
        if isinstance(location.get("bbox"), list) and len(location["bbox"]) == 4:
            return [float(x) for x in location["bbox"]]
        lat = location.get("lat")
        lon = location.get("lon")
        if lat is not None and lon is not None:
            return [float(lon) - 0.05, float(lat) - 0.05, float(lon) + 0.05, float(lat) + 0.05]
    raise ValueError("Search for a location or draw an AOI before analyzing.")


def _result_from_scene_analysis(category: str, analysis: Dict[str, Any], bbox: List[float], aoi_area_km2: float = 0.0) -> Dict[str, Any]:
    selected = _normalize_lc_class(category)
    scene = analysis.get("scene") or {}
    key_map = {
        "Water": ("water", "NDWI", "water", ["ndwi"]),
        "Agriculture": ("agriculture", "NDVI (0.18 - 0.45)", "agriculture", ["agriculture", "ndvi"]),
        "Forest / Vegetation": ("forest", "NDVI High Canopy (> 0.45)", "forest", ["forest", "ndvi"]),
        "Built-up": ("builtup", "NDBI", "builtup", ["builtup", "ndbi"]),
    }
    key, method, map_name, _ = key_map[selected]
    q = (analysis.get("quantitative_result") or {}).get(key) or {}
    if not q and selected == "Forest / Vegetation":
        q = (analysis.get("quantitative_result") or {}).get("vegetation_indicated") or {}
    geojson = (analysis.get("map_geojson") or {}).get(map_name) or {"type": "FeatureCollection", "features": []}
    
    # Calculate area_km2 and area_ha
    effective_aoi_km2 = float(analysis.get("aoi_area_km2") or aoi_area_km2 or 0.0)
    fraction = float(q.get("fraction", 0.0))
    area_km2 = float(q.get("area_km2", 0.0))
    if area_km2 <= 0.0 and fraction > 0.0 and effective_aoi_km2 > 0.0:
        area_km2 = round(fraction * effective_aoi_km2, 4)
    area_ha = float(area_km2 * 100.0)
    percentage = float(q.get("pct_approx", fraction * 100.0 if fraction else 0.0))
    pixel_count = int(q.get("pixel_count", fraction * max(1, int((analysis.get("shape") or [0, 0])[0] * (analysis.get("shape") or [0, 0])[1]))))
    
    return {
        "success": True,
        "mode": analysis.get("mode") or "RASTER",
        "quantitative_available": bool(analysis.get("mode") == "RASTER" and q),
        "selected_category": selected,
        "class": selected,
        "analysis_method": method,
        "method": method,
        "detected_pixel_count": pixel_count,
        "pixel_count": pixel_count,
        "area_km2": round(area_km2, 4),
        "area_ha": round(area_ha, 4),
        "aoi_area_ha": round(effective_aoi_km2 * 100.0, 4),
        "percentage_of_valid_pixels": round(percentage, 4),
        "percentage": round(percentage, 4),
        "bounds": {"left": float(bbox[0]), "bottom": float(bbox[1]), "right": float(bbox[2]), "top": float(bbox[3])},
        "crs": "EPSG:4326",
        "satellite": scene.get("satellite") or "Sentinel-2",
        "acquisition_date": scene.get("acquisition_date"),
        "cloud_cover_pct": scene.get("cloud_cover_pct"),
        "quality": {"confidence": "satellite spectral estimate" if pixel_count > 0 or percentage > 0 else "spectral calculation complete", "method_note": q.get("note") or "Satellite-based estimate from spectral index", "threshold": q.get("threshold") if isinstance(q, dict) else None},
        "statistics": q if isinstance(q, dict) else {},
        "geojson": geojson,
        "source": "Microsoft Planetary Computer STAC",
        "warning": "Real scene-based spectral estimate from Sentinel-2 COG reflectance.",
        "analysis_area": "active AOI",
    }


def _overview_from_analysis(analysis: Dict[str, Any], source: str) -> Dict[str, Any]:
    quantitative = analysis.get("quantitative_result") or {}
    category_specs = {
        "Water": ("water", "NDWI", "Green + NIR", "McFeeters NDWI > 0.0"),
        "Agriculture": ("agriculture", "NDVI", "Red + NIR", "NDVI > 0.18 and <= 0.45"),
        "Built-up": ("builtup", "NDBI", "SWIR16 + NIR", "NDBI > 0.0; includes bare-soil spectral responses"),
        "Forest / Vegetation": ("forest", "NDVI", "Red + NIR", "Dense-canopy estimate: NDVI > 0.45"),
    }
    scene = analysis.get("scene") or {}
    categories: Dict[str, Dict[str, Any]] = {}
    for name, (result_key, index, bands, method) in category_specs.items():
        measurement = quantitative.get(result_key)
        if measurement:
            categories[name] = {
                "available": True,
                "category": name,
                "index": index,
                "required_bands": bands,
                "method": measurement.get("method") or method,
                "area_km2": float(measurement.get("area_km2", 0.0)),
                "area_ha": float(measurement.get("area_ha", 0.0)),
                "percentage": float(measurement.get("pct_of_aoi", measurement.get("pct_approx", 0.0))),
                "pixel_count": int(measurement.get("pixel_count", 0)),
                "valid_pixel_count": int(measurement.get("valid_pixel_count", 0)),
                "valid_coverage_pct": float(measurement.get("valid_coverage_pct", 0.0)),
                "statistics": measurement,
                "quality": measurement.get("note"),
                "source": analysis.get("source") or source,
                "acquisition_date": scene.get("acquisition_date"),
            }
        else:
            missing = analysis.get("missing_bands") or analysis.get("fetch_details", {}).get("missing") or []
            reason = (
                f"Required bands unavailable: {', '.join(missing)}."
                if missing
                else analysis.get("fetch_error") or analysis.get("message") or "No valid pixels were available."
            )
            categories[name] = {
                "available": False,
                "category": name,
                "index": index,
                "required_bands": bands,
                "method": method,
                "message": reason,
            }
    return {
        "success": True,
        "mode": analysis.get("mode") or "RASTER",
        "quantitative_available": any(result["available"] for result in categories.values()),
        "selected_category": "Overall Measurement",
        "categories": categories,
        "source": analysis.get("source") or source,
        "satellite": scene.get("satellite"),
        "sensor": scene.get("sensor"),
        "acquisition_date": scene.get("acquisition_date"),
        "cloud_cover_pct": scene.get("cloud_cover_pct"),
        "message": analysis.get("message") or analysis.get("fetch_error"),
        "analysis_area": analysis.get("analysis_area") or "active AOI",
    }


@router.post("/analyze")
async def analyze_landcover(req: LandCoverRequest):
    category = req.category.strip()
    if not category:
        raise HTTPException(status_code=400, detail="Missing land-use category.")
    try:
        selected_category = _normalize_lc_class(category)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if req.aoi is not None:
        try:
            validate_polygon_geojson(req.aoi)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    image_id = (req.image_id or "").strip()
    if image_id:
        image_path = _resolve_uploaded_image(image_id)
        try:
            if selected_category == "Overall Measurement":
                categories: Dict[str, Dict[str, Any]] = {}
                for name in ("Water", "Agriculture", "Built-up", "Forest / Vegetation"):
                    try:
                        item = await run_in_threadpool(
                            analyze_uploaded_landcover, image_path, name, req.aoi
                        )
                        categories[name] = {
                            "available": True,
                            "category": name,
                            "index": item.get("quality", {}).get("index") or item.get("class"),
                            "required_bands": item.get("mask_size", {}).get("bands"),
                            "method": item.get("analysis_method"),
                            "area_km2": float(item.get("detected_area_sq_km", 0.0)),
                            "area_ha": float(item.get("area_ha", 0.0)),
                            "percentage": float(item.get("percentage", 0.0)),
                            "pixel_count": int(item.get("pixel_count", 0)),
                            "valid_pixel_count": int(item.get("valid_pixel_count", 0)),
                            "valid_coverage_pct": 100.0,
                            "statistics": item.get("statistics", {}),
                            "quality": item.get("quality", {}).get("method_note"),
                            "geojson": item.get("geojson"),
                        }
                    except LandCoverInputError as exc:
                        categories[name] = {
                            "available": False,
                            "category": name,
                            "message": str(exc),
                        }
                if not any(result["available"] for result in categories.values()):
                    raise LandCoverInputError(
                        "; ".join(f"{name}: {result['message']}" for name, result in categories.items())
                    )
                result = {
                    "success": True,
                    "mode": "RASTER",
                    "quantitative_available": True,
                    "selected_category": "Overall Measurement",
                    "categories": categories,
                    "source": "User-uploaded multispectral GeoTIFF",
                    "acquisition_date": None,
                    "message": "Measurements use only categories supported by the uploaded GeoTIFF bands.",
                    "analysis_area": "manual polygon" if req.aoi else "uploaded raster extent",
                }
                result_id = str(uuid4())
                result["analysis_id"] = result_id
                result["overlay_url"] = f"/api/analysis-result/{result_id}"
                _analysis_store[result_id] = result
                return result

            result = await run_in_threadpool(
                analyze_uploaded_landcover, image_path, category, req.aoi
            )
            result_id = str(uuid4())
            result["analysis_id"] = result_id
            result["class"] = result.get("selected_category") or category
            result["area_ha"] = float(result.get("area_ha", result.get("detected_area_sq_km", 0.0) * 100.0))
            result["percentage"] = float(result.get("percentage", result.get("percentage_of_valid_pixels", 0.0)))
            result["pixel_count"] = int(result.get("pixel_count", result.get("detected_pixel_count", 0)))
            result["overlay_url"] = f"/api/analysis-result/{result_id}"
            _analysis_store[result_id] = result
            return {"success": True, **result}
        except LandCoverInputError as exc:
            logger.warning("Land-cover input rejected: %s", exc)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Unexpected uploaded land-cover analysis failure")
            raise HTTPException(
                status_code=500,
                detail="Land-cover analysis failed because of an internal processing error.",
            ) from exc

    try:
        bbox = _bbox_from_request(req.aoi, req.location, req.bbox)
        scene_result = await get_best_optical_scene(bbox)
        if not scene_result.get("success") or not scene_result.get("scene"):
            detail = scene_result.get("error") or "Satellite imagery is unavailable for this AOI."
            if scene_result.get("search_result"):
                raise HTTPException(
                    status_code=503,
                    detail="Satellite catalog is temporarily unavailable. Please try again shortly.",
                )
            raise HTTPException(
                status_code=404,
                detail=f"No suitable satellite imagery was found for this AOI. {detail}",
            )
        aoi_area_km2 = 0.0
        if req.aoi is not None:
            if shape is None:
                raise ValueError("AOI support requires Shapely.")
            from backend.processing.area_calculation import aoi_area_from_geojson
            aoi_area_km2 = float(aoi_area_from_geojson(req.aoi))
        else:
            try:
                from backend.processing.area_calculation import aoi_area_from_bbox
                aoi_area_km2 = aoi_area_from_bbox(bbox)
            except Exception:
                aoi_area_km2 = 0.0

        selected = selected_category
        analysis_map = {
            "Water": ["ndwi"],
            "Agriculture": ["ndvi"],
            "Forest / Vegetation": ["ndvi"],
            "Built-up": ["ndbi"],
            "Overall Measurement": ["ndwi", "ndvi", "ndbi"],
        }

        result = None
        scene = None
        fetch_errors = []
        for candidate in scene_result.get("candidates") or [scene_result["scene"]]:
            candidate_result = await run_in_threadpool(
                analyze_optical_aoi,
                candidate,
                bbox,
                aoi_area_km2,
                analysis_map[selected],
                req.aoi,
            )
            if candidate_result.get("success") and candidate_result.get("quantitative_result"):
                result = candidate_result
                scene = candidate
                break
            fetch_errors.append(candidate_result.get("fetch_error") or candidate_result.get("error") or "No valid index pixels.")
        if result is None or scene is None:
            logger.warning(
                "No usable land-cover result for AOI after %s candidate scenes: %s",
                len(fetch_errors),
                fetch_errors,
            )
            raise HTTPException(
                status_code=502,
                detail="No usable satellite bands or valid pixels were available for this AOI in the searched date range. Try a smaller AOI or another location.",
            )
        normalized = (
            _overview_from_analysis(result, "Microsoft Planetary Computer")
            if selected == "Overall Measurement"
            else _result_from_scene_analysis(category, result, bbox, aoi_area_km2=aoi_area_km2)
        )
        result_id = str(uuid4())
        normalized["analysis_id"] = result_id
        normalized["overlay_url"] = f"/api/analysis-result/{result_id}"
        _analysis_store[result_id] = normalized
        return {"success": True, **normalized}
    except HTTPException:
        raise
    except ValueError as exc:
        logger.warning("Land-cover request could not be processed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected land-cover analysis failure")
        raise HTTPException(
            status_code=500,
            detail="Land-cover analysis failed because of an internal processing error.",
        ) from exc


@router.get("/supported")
async def supported_categories() -> Dict[str, Any]:
    return {
        "success": True,
        "categories": [
            {"name": "Overall Measurement", "required_bands": ["green", "red", "nir", "swir16"], "method": "NDWI, NDVI estimate, NDBI, and high-NDVI canopy estimate"},
            {"name": "Water", "required_bands": ["green", "nir"], "method": "NDWI"},
            {"name": "Agriculture", "required_bands": ["red", "nir"], "method": "NDVI threshold"},
            {"name": "Forest / Vegetation", "required_bands": ["red", "nir"], "method": "NDVI threshold"},
            {"name": "Built-up", "required_bands": ["swir16", "nir"], "method": "NDBI"},
        ],
    }


@legacy_router.post("/api/upload-geotiff")
async def upload_geotiff_alias(file: UploadFile = File(...)):
    return await upload_geotiff_route(file)


@legacy_router.post("/api/analyze-land-cover")
async def analyze_landcover_alias(req: LandCoverRequest):
    return await analyze_landcover(req)


@legacy_router.post("/api/clear-analysis")
async def clear_analysis():
    _analysis_store.clear()
    return {"success": True, "message": "Analysis overlay cleared."}


@legacy_router.get("/api/analysis-result/{analysis_id}")
async def get_analysis_result(analysis_id: str):
    result = _analysis_store.get(analysis_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Analysis result not found.")
    return {"success": True, **result}
