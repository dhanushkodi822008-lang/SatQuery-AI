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


from backend.db.models import EnvironmentalData, get_db
from backend.ai.ml_predict import predict_future_metrics
from sqlalchemy.orm import Session
from fastapi import Depends

class PredictRequest(BaseModel):
    location: str = Field(..., min_length=1, max_length=300)
    latitude: float
    longitude: float
    temperature: Optional[float] = None
    rainfall: Optional[float] = None
    ndvi: Optional[float] = None
    ndwi: Optional[float] = None

@router.post("/predict")
async def predict_metrics(req: PredictRequest, db: Session = Depends(get_db)):
    # 1. Store the new real-time data
    new_data = EnvironmentalData(
        location_name=req.location,
        latitude=req.latitude,
        longitude=req.longitude,
        temperature=req.temperature,
        rainfall=req.rainfall,
        ndvi=req.ndvi,
        ndwi=req.ndwi,
        source="API Request"
    )
    db.add(new_data)
    db.commit()
    
    # 2. Fetch historical data for this location
    hist_records = db.query(EnvironmentalData).filter(EnvironmentalData.location_name == req.location).order_by(EnvironmentalData.timestamp.asc()).all()
    
    historical_data = []
    for r in hist_records:
        historical_data.append({
            "timestamp": r.timestamp,
            "temperature": r.temperature,
            "rainfall": r.rainfall,
            "ndvi": r.ndvi,
            "ndwi": r.ndwi
        })
        
    current_data = {
        "temperature": req.temperature,
        "rainfall": req.rainfall,
        "ndvi": req.ndvi,
        "ndwi": req.ndwi
    }
    
    # 3. Call ML model
    prediction_result = predict_future_metrics(historical_data, current_data)
    
    return {
        "success": True,
        "location": req.location,
        "historical_records_count": len(historical_data),
        "prediction": prediction_result
    }

@router.get("/models")
async def models():
    return {"models": list_models()}
