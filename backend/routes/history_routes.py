"""Durable analysis history used by the Data & Reports page."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db.models import AnalysisRecord, get_db

router = APIRouter(prefix="/api/history", tags=["history"])


class HistoryCreate(BaseModel):
    analysis_type: str = Field(..., min_length=1, max_length=128)
    location_name: Optional[str] = Field(None, max_length=512)
    status: str = Field("READY", min_length=1, max_length=32)
    result: Dict[str, Any] = Field(default_factory=dict)


def _json_safe(value: Any) -> Any:
    """Round-trip API results so dates and numpy scalars never break SQLite."""
    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError):
        return {"value": str(value)}


def _serialize(row: AnalysisRecord) -> Dict[str, Any]:
    return {
        "id": row.id,
        "analysis_type": row.analysis_type,
        "location_name": row.location_name,
        "status": row.status,
        "result": row.result_json or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.post("", status_code=201)
async def create_history(item: HistoryCreate, db: Session = Depends(get_db)):
    row = AnalysisRecord(
        analysis_type=item.analysis_type,
        location_name=item.location_name,
        status=item.status.upper(),
        result_json=_json_safe(item.result),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"success": True, "record": _serialize(row)}


@router.get("")
async def list_history(
    location_name: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(AnalysisRecord).order_by(AnalysisRecord.created_at.desc())
    if location_name:
        query = query.filter(AnalysisRecord.location_name == location_name)
    rows: List[AnalysisRecord] = query.limit(limit).all()
    return {"success": True, "records": [_serialize(row) for row in rows]}