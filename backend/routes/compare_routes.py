from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.comparison_service import compare_images
from backend.services.satellite_service import (
    compare_scenes_by_dates,
    compare_scenes_by_years,
    available_years_for_aoi,
)
from backend.services.geocoding_service import geocode

router = APIRouter(prefix="/api/compare", tags=["compare"])


class CompareRequest(BaseModel):
    image_before_id: str
    image_after_id: str


class DateCompareRequest(BaseModel):
    date_a: str = Field(..., description="YYYY-MM-DD")
    date_b: str = Field(..., description="YYYY-MM-DD")
    location: Optional[str] = None
    bbox: Optional[List[float]] = None
    aoi: Optional[Any] = None
    window_days: int = Field(14, ge=1, le=60)
    max_cloud: float = Field(40.0, ge=0, le=100)
    index: Optional[str] = Field(None, description="ndvi | ndwi | ndbi | evi | savi")
    collection: Optional[str] = None


class YearCompareRequest(BaseModel):
    year_a: int = Field(..., ge=2015, le=2030)
    year_b: int = Field(..., ge=2015, le=2030)
    location: Optional[str] = None
    bbox: Optional[List[float]] = None
    aoi: Optional[Any] = None
    max_cloud: float = Field(40.0, ge=0, le=100)
    index: Optional[str] = None
    collection: Optional[str] = None


async def _resolve_bbox(
    location: Optional[str],
    bbox: Optional[List[float]],
    aoi: Optional[Any],
) -> List[float]:
    if bbox and len(bbox) == 4:
        return bbox
    if aoi:
        try:
            if isinstance(aoi, dict) and aoi.get("type") == "Polygon":
                coords = aoi["coordinates"][0]
                lons = [c[0] for c in coords]
                lats = [c[1] for c in coords]
                return [min(lons), min(lats), max(lons), max(lats)]
            if isinstance(aoi, list) and aoi:
                lons, lats = [], []
                for p in aoi:
                    if isinstance(p, dict):
                        lats.append(float(p.get("lat")))
                        lons.append(float(p.get("lon")))
                    elif isinstance(p, (list, tuple)) and len(p) >= 2:
                        lons.append(float(p[0]))
                        lats.append(float(p[1]))
                if lons and lats:
                    return [min(lons), min(lats), max(lons), max(lats)]
        except Exception:
            pass
    if location:
        geo = await geocode(location)
        if not geo.get("success"):
            raise HTTPException(
                status_code=400,
                detail=geo.get("error") or f"Could not geocode location: {location}",
            )
        if geo.get("bbox"):
            return geo["bbox"]
        lat = float(geo["lat"])
        lon = float(geo["lon"])
        d = 0.05
        return [lon - d, lat - d, lon + d, lat + d]
    raise HTTPException(
        status_code=400,
        detail="Provide location, bbox [min_lon,min_lat,max_lon,max_lat], or aoi.",
    )


@router.post("/")
@router.post("/images")
async def compare_two_images(req: CompareRequest):
    try:
        result = compare_images(req.image_before_id, req.image_after_id)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Comparison failed"))
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.post("/dates")
async def compare_by_dates(req: DateCompareRequest):
    bbox = await _resolve_bbox(req.location, req.bbox, req.aoi)
    collections = None
    if req.collection and req.collection.lower() not in ("auto", ""):
        collections = [c.strip() for c in req.collection.split(",") if c.strip()]
    try:
        # Temporarily pass collections via get_best if needed — compare_scenes_by_dates uses default
        result = await compare_scenes_by_dates(
            bbox=bbox,
            date_a=req.date_a.strip(),
            date_b=req.date_b.strip(),
            window_days=req.window_days,
            max_cloud=req.max_cloud,
            index=req.index,
        )
        result["mode"] = "specific_dates"
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Date comparison failed: {type(e).__name__}: {e}")


@router.post("/years")
async def compare_by_years(req: YearCompareRequest):
    bbox = await _resolve_bbox(req.location, req.bbox, req.aoi)
    collections = None
    if req.collection and req.collection.lower() not in ("auto", ""):
        collections = [c.strip() for c in req.collection.split(",") if c.strip()]
    try:
        result = await compare_scenes_by_years(
            bbox=bbox,
            year_a=req.year_a,
            year_b=req.year_b,
            max_cloud=req.max_cloud,
            index=req.index,
            collections=collections,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Year comparison failed: {type(e).__name__}: {e}")


@router.get("/available-years")
async def available_years(
    min_lon: Optional[float] = None,
    min_lat: Optional[float] = None,
    max_lon: Optional[float] = None,
    max_lat: Optional[float] = None,
    location: Optional[str] = None,
    collection: Optional[str] = "sentinel-2-l2a,landsat-c2-l2",
    max_cloud: float = 80.0,
    min_year: int = 2015,
    max_year: Optional[int] = None,
):
    bbox = None
    if all(v is not None for v in (min_lon, min_lat, max_lon, max_lat)):
        bbox = [min_lon, min_lat, max_lon, max_lat]
    else:
        bbox = await _resolve_bbox(location, None, None)
    collections = [c.strip() for c in (collection or "").split(",") if c.strip()] or [
        "sentinel-2-l2a",
        "landsat-c2-l2",
    ]
    return await available_years_for_aoi(
        bbox=bbox,
        collections=collections,
        max_cloud=max_cloud,
        min_year=min_year,
        max_year=max_year,
    )
