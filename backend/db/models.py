"""SQLAlchemy models for chat sessions and messages."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    Float,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from backend.config import get_settings

Base = declarative_base()


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(64), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    title = Column(String(256), nullable=True)
    aoi_json = Column(JSON, nullable=True)
    image_id = Column(String(64), nullable=True)
    location = Column(String(512), nullable=True)

    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    analyses = relationship("Analysis", back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("sessions.id"), index=True)
    role = Column(String(16), nullable=False)  # user | assistant | system
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    meta_json = Column(JSON, nullable=True)  # evidence, trace, confidence, etc.

    session = relationship("Session", back_populates="messages")


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("sessions.id"), index=True)
    task = Column(String(64), nullable=True)
    result_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("Session", back_populates="analyses")


class AnalysisRecord(Base):
    """Durable history for completed product workflows.

    Chat analyses are tied to a chat session, but satellite, land-cover, and
    change workflows can be completed without opening a chat.  This separate
    table keeps those results available to Data & Reports after a reload.
    """

    __tablename__ = "analysis_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_type = Column(String(128), nullable=False)
    location_name = Column(String(512), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="READY")
    result_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class EnvironmentalData(Base):
    __tablename__ = "environmental_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_name = Column(String(256), index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Real-time metrics
    ndvi = Column(Float, nullable=True)
    ndwi = Column(Float, nullable=True)
    temperature = Column(Float, nullable=True)
    rainfall = Column(Float, nullable=True)
    
    source = Column(String(128), nullable=True)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_name = Column(String(256), nullable=False)
    condition_type = Column(String(128), nullable=False)  # e.g., 'vegetation_decrease'
    threshold = Column(Float, nullable=False)
    email = Column(String(256), nullable=True)
    phone = Column(String(64), nullable=True)
    active = Column(Integer, default=1)  # 1 for active, 0 for inactive
    # Exact user-drawn AOI polygon (GeoJSON Geometry or Feature/FeatureCollection)
    aoi_geojson = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    history = relationship("AlertHistory", back_populates="alert", cascade="all, delete-orphan")


class AlertHistory(Base):
    __tablename__ = "alert_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    condition_detected = Column(String(256), nullable=False)
    notification_type = Column(String(64), nullable=False)  # 'email', 'sms'
    status = Column(String(64), nullable=False)  # 'success', 'failed'
    error_message = Column(Text, nullable=True)

    alert = relationship("Alert", back_populates="history")



_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        if settings.DATABASE_URL:
            # Use PostgreSQL (Supabase or other)
            _engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
        else:
            # Fallback to SQLite
            db_path = Path("/tmp/satquery.db")
            db_path.parent.mkdir(parents=True, exist_ok=True)
            _engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
            
        Base.metadata.create_all(_engine)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def get_db():
    get_engine()
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_alert_aoi_column(engine) -> None:
    """Add aoi_geojson to existing SQLite alerts table if missing (create_all does not alter)."""
    try:
        from sqlalchemy import text, inspect

        insp = inspect(engine)
        if "alerts" not in insp.get_table_names():
            return
        cols = {c["name"] for c in insp.get_columns("alerts")}
        if "aoi_geojson" in cols:
            return
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE alerts ADD COLUMN aoi_geojson JSON"))
    except Exception:
        pass  # non-fatal; fresh create_all will include the column


def init_db():
    engine = get_engine()
    _ensure_alert_aoi_column(engine)
