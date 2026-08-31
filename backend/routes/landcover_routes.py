from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.processing.raster_processing import analyze_optical_aoi
from backend.routes.image_routes import upload_image as upload_geotiff_route
from backend.services.landcover_service import analyze_uploaded_landcover
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


def _result_from_scene_analysis(category: str, analysis: Dict[str, Any], bbox: List[float]) -> Dict[str, Any]:
    selected = _normalize_lc_class(category)
    scene = analysis.get("scene") or {}
    key_map = {
        "Water": ("water", "NDWI", "water", ["ndwi"]),
        "Agriculture": ("vegetation_indicated", "NDVI", "vegetation", ["ndvi"]),
        "Forest / Vegetation": ("vegetation_indicated", "NDVI", "vegetation", ["ndvi"]),
        "Built-up": ("builtup_indicated", "NDBI", "builtup", ["ndbi"]),
    }
    key, method, map_name, analyses = key_map[selected]
    q = (analysis.get("quantitative_result") or {}).get(key) or {}
    geojson = (analysis.get("map_geojson") or {}).get(map_name) or {"type": "FeatureCollection", "features": []}
    area_ha = float(q.get("area_km2", 0.0) * 100.0) if q.get("area_km2") is not None else 0.0
    percentage = float(q.get("pct_approx", q.get("fraction", 0.0) * 100.0 if q.get("fraction") is not None else 0.0))
    pixel_count = int(q.get("pixel_count", q.get("fraction", 0.0) * max(1, int((analysis.get("shape") or [0, 0])[0] * (analysis.get("shape") or [0, 0])[1]))))
    if selected in {"Agriculture", "Forest / Vegetation"} and not q:
        raise ValueError("No vegetation pixels met the threshold in the selected satellite scene.")
    if selected == "Built-up" and not q:
        raise ValueError("Built-up detection could not be computed from the available satellite scene.")
    return {
        "success": True,
        "selected_category": selected,
        "class": selected,
        "analysis_method": method,
        "method": method,
        "detected_pixel_count": pixel_count,
        "pixel_count": pixel_count,
        "area_ha": round(area_ha, 4),
        "aoi_area_ha": round(float((analysis.get("aoi_area_km2") or 0.0) * 100.0), 4),
        "percentage_of_valid_pixels": round(percentage, 4),
        "percentage": round(percentage, 4),
        "bounds": {"left": float(bbox[0]), "bottom": float(bbox[1]), "right": float(bbox[2]), "top": float(bbox[3])},
        "crs": "EPSG:4326",
        "satellite": scene.get("satellite") or "Sentinel-2",
        "acquisition_date": scene.get("acquisition_date"),
        "cloud_cover_pct": scene.get("cloud_cover_pct"),
        "quality": {"confidence": "satellite spectral estimate" if pixel_count > 0 else "low confidence / no strong detection", "method_note": q.get("note") or "Satellite-based estimate from spectral index", "threshold": q.get("threshold") if isinstance(q, dict) else None},
        "statistics": q if isinstance(q, dict) else {},
        "geojson": geojson,
        "source": "Microsoft Planetary Computer STAC",
        "warning": "This is a real scene-based spectral estimate, not a trained land-use classifier.",
        "analysis_area": "automatic location AOI",
        "aoi": req.aoi if 'req' in globals() else None,
    }


@router.post("/analyze")
async def analyze_landcover(req: LandCoverRequest):
    category = req.category.strip()
    if not category:
        raise HTTPException(status_code=400, detail="Missing land-use category.")

    if req.aoi is not None:
        try:
            validate_polygon_geojson(req.aoi)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    image_id = (req.image_id or "").strip()
    if image_id:
        image_path = _resolve_uploaded_image(image_id)
        try:
            result = analyze_uploaded_landcover(image_path, category, req.aoi)
            result_id = str(uuid4())
            result["analysis_id"] = result_id
            result["class"] = result.get("selected_category") or category
            result["area_ha"] = float(result.get("area_ha", result.get("detected_area_sq_km", 0.0) * 100.0))
            result["percentage"] = float(result.get("percentage", result.get("percentage_of_valid_pixels", 0.0)))
            result["pixel_count"] = int(result.get("pixel_count", result.get("detected_pixel_count", 0)))
            result["overlay_url"] = f"/api/analysis-result/{result_id}"
            _analysis_store[result_id] = result
            return {"success": True, **result}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Land-use analysis failed: {exc}") from exc

    try:
        bbox = _bbox_from_request(req.aoi, req.location, req.bbox)
        scene_result = await get_best_optical_scene(bbox)
        if not scene_result.get("success") or not scene_result.get("scene"):
            raise ValueError("No suitable satellite imagery was found for this location.")
        scene = scene_result["scene"]
        aoi_area_km2 = 0.0
        if req.aoi is not None:
            if shape is None:
                raise ValueError("AOI support requires Shapely.")
            aoi_area_km2 = float(shape(req.aoi).area / 1_000_000.0) * 111_000.0
        else:
            try:
                from backend.processing.area_calculation import aoi_area_from_bbox
                aoi_area_km2 = aoi_area_from_bbox(bbox)
            except Exception:
                aoi_area_km2 = 0.0

        analyses = []
        selected = _normalize_lc_class(category)
        if selected == "Water":
            analyses = ["ndwi"]
        elif selected in {"Agriculture", "Forest / Vegetation"}:
            analyses = ["ndvi"]
        elif selected == "Built-up":
            analyses = ["ndbi"]

        result = analyze_optical_aoi(scene, bbox, aoi_area_km2, analyses=analyses, aoi_geojson=req.aoi)
        if not result.get("success"):
            raise ValueError(result.get("error") or "Satellite image analysis could not be completed.")
        normalized = _result_from_scene_analysis(category, result, bbox)
        result_id = str(uuid4())
        normalized["analysis_id"] = result_id
        normalized["overlay_url"] = f"/api/analysis-result/{result_id}"
        _analysis_store[result_id] = normalized
        return {"success": True, **normalized}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Land-use analysis failed: {exc}") from exc


@router.get("/supported")
async def supported_categories() -> Dict[str, Any]:
    return {
        "success": True,
        "categories": [
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
