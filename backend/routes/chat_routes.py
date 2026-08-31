"""Session-based multi-turn chat for SatQuery AI."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from backend.db.models import Session as ChatSession, Message, Analysis, get_engine, init_db
from backend.db.models import get_db
from backend.services.data_fusion_service import analyze_query
from backend.ai.vqa import answer_vqa
from backend.ai.grounding import ground_phrase
from backend.ai.query_router import route_query
from backend.utils.validation import sanitize_query
from backend.utils.logging import logger

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Ensure tables exist
init_db()


class ChatMessageRequest(BaseModel):
    session_id: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=1000)
    image_id: Optional[str] = None
    aoi: Optional[Dict[str, Any]] = None
    location: Optional[str] = None


def _get_session(db: DBSession, session_id: str) -> ChatSession:
    s = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return s


def _history_for_vlm(db: DBSession, session_id: str, limit: int = 8) -> List[Dict[str, str]]:
    msgs = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.id.desc())
        .limit(limit)
        .all()
    )
    msgs = list(reversed(msgs))
    return [{"role": m.role, "content": m.content} for m in msgs]


@router.post("/message")
async def chat_message(req: ChatMessageRequest):
    from sqlalchemy.orm import sessionmaker
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        message = sanitize_query(req.message, 1000)
        session_id = req.session_id or uuid.uuid4().hex

        sess = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not sess:
            sess = ChatSession(
                id=session_id,
                title=message[:80],
                image_id=req.image_id,
                location=req.location,
                aoi_json=req.aoi,
            )
            db.add(sess)
            db.commit()
        else:
            if req.image_id:
                sess.image_id = req.image_id
            if req.location:
                sess.location = req.location
            if req.aoi is not None:
                sess.aoi_json = req.aoi
            sess.updated_at = datetime.utcnow()
            db.commit()

        # Store user message
        user_msg = Message(session_id=session_id, role="user", content=message)
        db.add(user_msg)
        db.commit()

        history = _history_for_vlm(db, session_id)
        routing = route_query(message)
        task = routing.get("detected_task", "vqa")

        location = req.location or sess.location or "India"
        image_id = req.image_id or sess.image_id
        aoi = req.aoi if req.aoi is not None else sess.aoi_json

        # Prefer full analyze_query for location-based tools; VQA/grounding get extra path
        result: Dict[str, Any] = {}
        try:
            if task in ("vqa", "captioning") or image_id:
                # Run analyze for context + VQA
                analysis = await analyze_query(location, message, aoi)
                ctx = {
                    "display_name": (analysis.get("location") or {}).get("display_name"),
                    "aoi_area_km2": (analysis.get("location") or {}).get("aoi_area_km2"),
                    "scene": (analysis.get("satellite_optical") or {}).get("scene"),
                    "metrics": analysis.get("metrics") or {},
                    "image_id": image_id,
                    "optical_analysis": analysis.get("optical_analysis"),
                }
                if task == "grounding" or "show me where" in message.lower():
                    ground = await ground_phrase(message, ctx)
                    answer_text = ground.get("message") or (
                        f"Grounded '{ground.get('target')}' — area ≈ {ground.get('area_km2')} km² "
                        f"(method={ground.get('method')}, confidence={ground.get('confidence')})."
                    )
                    result = {
                        "success": ground.get("success", False),
                        "answer_text": answer_text,
                        "grounding": ground,
                        "analysis": analysis,
                        "detected_task": "grounding",
                        "execution_trace": analysis.get("execution_trace", []),
                        "evidence": ground.get("threshold"),
                        "confidence": ground.get("confidence"),
                    }
                else:
                    vqa = await answer_vqa(message, ctx, history=history)
                    result = {
                        "success": vqa.get("success", True),
                        "answer_text": vqa.get("answer") or analysis.get("answer_text"),
                        "vqa": vqa,
                        "analysis": analysis,
                        "detected_task": task,
                        "execution_trace": analysis.get("execution_trace", []),
                        "evidence": vqa.get("evidence"),
                        "confidence": vqa.get("confidence"),
                        "sources": vqa.get("sources"),
                    }
            else:
                analysis = await analyze_query(location, message, aoi)
                result = {
                    "success": analysis.get("success", True),
                    "answer_text": analysis.get("answer_text"),
                    "analysis": analysis,
                    "detected_task": task,
                    "execution_trace": analysis.get("execution_trace", []),
                    "metrics": analysis.get("metrics"),
                    "confidence": analysis.get("confidence"),
                    "sources": analysis.get("sources"),
                    "map_layers": analysis.get("map_layers"),
                }
        except Exception as exc:
            logger.exception("chat message failed")
            result = {
                "success": False,
                "answer_text": f"Error processing message: {exc}",
                "detected_task": task,
            }

        answer_text = result.get("answer_text") or "No answer generated."
        assistant_msg = Message(
            session_id=session_id,
            role="assistant",
            content=answer_text,
            meta_json={
                "task": result.get("detected_task"),
                "confidence": result.get("confidence"),
                "evidence": result.get("evidence"),
                "execution_trace": result.get("execution_trace"),
                "sources": result.get("sources"),
            },
        )
        db.add(assistant_msg)
        analysis_row = Analysis(
            session_id=session_id,
            task=result.get("detected_task"),
            result_json={k: v for k, v in result.items() if k not in ("analysis",)},
        )
        db.add(analysis_row)
        db.commit()

        return {
            "session_id": session_id,
            "message_id": assistant_msg.id,
            "role": "assistant",
            "content": answer_text,
            "task": result.get("detected_task"),
            "confidence": result.get("confidence"),
            "evidence": result.get("evidence"),
            "execution_trace": result.get("execution_trace"),
            "grounding": result.get("grounding"),
            "vqa": result.get("vqa"),
            "map_layers": result.get("map_layers") or (result.get("analysis") or {}).get("map_layers"),
            "metrics": result.get("metrics") or (result.get("analysis") or {}).get("metrics"),
            "sources": result.get("sources"),
            "success": result.get("success", True),
        }
    finally:
        db.close()


@router.get("/history/{session_id}")
async def chat_history(session_id: str):
    from sqlalchemy.orm import sessionmaker
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        sess = _get_session(db, session_id)
        msgs = (
            db.query(Message)
            .filter(Message.session_id == session_id)
            .order_by(Message.id.asc())
            .all()
        )
        return {
            "session_id": session_id,
            "location": sess.location,
            "image_id": sess.image_id,
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "meta": m.meta_json,
                }
                for m in msgs
            ],
        }
    finally:
        db.close()


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    from sqlalchemy.orm import sessionmaker
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        sess = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not sess:
            raise HTTPException(status_code=404, detail="Session not found")
        db.delete(sess)
        db.commit()
        return {"success": True, "deleted": session_id}
    finally:
        db.close()


@router.get("/sessions")
async def list_sessions(limit: int = 20):
    from sqlalchemy.orm import sessionmaker
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        rows = (
            db.query(ChatSession)
            .order_by(ChatSession.updated_at.desc())
            .limit(limit)
            .all()
        )
        return {
            "sessions": [
                {
                    "id": s.id,
                    "title": s.title,
                    "location": s.location,
                    "image_id": s.image_id,
                    "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                }
                for s in rows
            ]
        }
    finally:
        db.close()
