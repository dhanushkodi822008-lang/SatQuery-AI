from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from backend.services.data_fusion_service import analyze_query
from backend.ai.model_registry import list_models
from backend.utils.validation import sanitize_query, validate_polygon_geojson

router = APIRouter(prefix="/api/analyze", tags=["analysis"])


class QueryRequest(BaseModel):
    location: str = Field(..., min_length=1, max_length=300)
    question: str = Field(..., min_length=1, max_length=500)
    aoi: Optional[Dict[str, Any]] = None


@router.post("/query")
async def analyze(req: QueryRequest):
    location = sanitize_query(req.location, 300)
    question = sanitize_query(req.question, 500)
    if req.aoi is not None:
        try:
            validate_polygon_geojson(req.aoi)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await analyze_query(location, question, req.aoi)


@router.get("/models")
async def models():
    return {"models": list_models()}
