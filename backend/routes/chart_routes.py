from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.services.chart_service import chart_data_request

router = APIRouter(prefix="/api/chart", tags=["chart"])


class ChartDataRequest(BaseModel):
    location: Optional[str] = None
    aoi: Optional[Any] = None
    bbox: Optional[List[float]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    index: Optional[str] = Field(None, description="NDVI | NDWI | NDBI | EVI | SAVI")
    metric: str = "mean"
    satellite: str = "auto"


@router.post("/data")
async def post_chart_data(req: ChartDataRequest):
    return await chart_data_request(
        location=req.location,
        bbox=req.bbox,
        start_year=req.start_year,
        end_year=req.end_year,
        start_date=req.start_date,
        end_date=req.end_date,
        index=req.index,
        metric=req.metric,
        satellite=req.satellite,
    )
