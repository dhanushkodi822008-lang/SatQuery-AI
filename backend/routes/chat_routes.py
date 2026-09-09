"""
Session-based multi-turn chat for SatQuery AI.
Integrates Groq AI, the 2,297-question KnowledgeEngine (RAG), and real STAC satellite evidence.
Dispatches real actions (location finding, real administrative boundary selection, AOI changes, basemap switches, index calculations).
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from backend.config import get_settings
from backend.db.models import Session as ChatSession, Message, Analysis, get_engine, init_db
from backend.services.data_fusion_service import analyze_query
from backend.services.geocoding_service import geocode, geocode_coordinates
from backend.services.landcover_service import analyze_visual_satellite_image
from backend.ai.vqa import answer_vqa
from backend.ai.grounding import ground_phrase
from backend.ai.query_router import route_query
from backend.ai.knowledge_engine import search_knowledge, get_knowledge_engine
from backend.ai.vlm_provider import run_vlm
from backend.utils.validation import sanitize_query, parse_coordinates
from backend.utils.logging import logger

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Ensure database tables exist
init_db()


class ChatMessageRequest(BaseModel):
    session_id: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=1000)
    image_id: Optional[str] = None
    aoi: Optional[Dict[str, Any]] = None
    location: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    bbox: Optional[List[float]] = None
    context: Optional[Dict[str, Any]] = None


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


def _extract_analysis_evidence(analysis: Dict[str, Any], query: str, location: str, extra_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    evidence: Dict[str, Any] = {}
    loc = analysis.get("location") or {}
    evidence["location"] = loc.get("display_name") or location
    if loc.get("lat") is not None and loc.get("lon") is not None:
        evidence["coordinates"] = f"Latitude: {loc['lat']}, Longitude: {loc['lon']}"

    aoi_km2 = loc.get("aoi_area_km2") or loc.get("area_km2") or (analysis.get("metrics") or {}).get("aoi_km2")
    if aoi_km2 is not None:
        evidence["aoi_area_km2"] = round(float(aoi_km2), 4)
        evidence["aoi_area_sqft"] = round(float(aoi_km2) * 10_763_910.41671, 2)
        evidence["aoi_area_hectares"] = round(float(aoi_km2) * 100.0, 2)

    scene = (analysis.get("satellite_optical") or {}).get("scene") or {}
    if scene:
        evidence["satellite"] = scene.get("satellite") or "Sentinel-2"
        evidence["sensor"] = scene.get("sensor") or "MSI"
        evidence["acquisition_date"] = scene.get("acquisition_date")
        evidence["scene_date"] = scene.get("acquisition_date")
        evidence["cloud_cover_pct"] = round(float(scene.get("cloud_cover_pct", 0)), 2)
        evidence["resolution_m"] = scene.get("resolution_m") or 10.0
        evidence["scene_id"] = scene.get("id")

    # Comparison evidence
    cmp_ctx = (extra_context or {}).get("comparison") or (extra_context or {}).get("change") or analysis.get("change") or {}
    if cmp_ctx:
        if cmp_ctx.get("summary_a") and cmp_ctx.get("summary_b"):
            sa, sb = cmp_ctx["summary_a"], cmp_ctx["summary_b"]
            evidence["comparison_period"] = f"Period A ({sa.get('acquisition_date') or sa.get('year')}) vs Period B ({sb.get('acquisition_date') or sb.get('year')})"
            evidence["before_observation"] = f"Date: {sa.get('acquisition_date')}, Cloud: {sa.get('cloud_cover_pct')}%, Sensor: {sa.get('satellite')}"
            evidence["after_observation"] = f"Date: {sb.get('acquisition_date')}, Cloud: {sb.get('cloud_cover_pct')}%, Sensor: {sb.get('satellite')}"
        if cmp_ctx.get("change_pct") is not None or cmp_ctx.get("percentage_change") is not None:
            pct = cmp_ctx.get("change_pct", cmp_ctx.get("percentage_change"))
            evidence["detected_change_percentage"] = f"{pct}%"
        if cmp_ctx.get("area_changed_km2") is not None:
            c_km2 = float(cmp_ctx["area_changed_km2"])
            evidence["detected_area_change_km2"] = c_km2
            evidence["detected_area_change_sqft"] = round(c_km2 * 10_763_910.41671, 2)
            evidence["detected_area_change_hectares"] = round(c_km2 * 100.0, 2)
        if cmp_ctx.get("change_type") or cmp_ctx.get("detected_change"):
            evidence["change_classification"] = cmp_ctx.get("change_type") or cmp_ctx.get("detected_change")

    # Landcover / indices evidence
    sat_opt = analysis.get("optical_analysis") or (analysis.get("satellite_optical") or {}).get("analysis") or {}
    if sat_opt.get("ndvi"):
        ndvi_m = sat_opt["ndvi"].get("mean")
        if ndvi_m is not None:
            evidence["ndvi_mean"] = round(float(ndvi_m), 4)
            evidence["ndvi_formula"] = "NDVI = (NIR - RED) / (NIR + RED)"

    sat_water = analysis.get("satellite_water") or {}
    q_water = (sat_water.get("quantitative_result") or {}).get("water") or {}
    if q_water:
        evidence["water_area_km2"] = q_water.get("area_km2")
        evidence["ndwi_formula"] = "NDWI = (GREEN - NIR) / (GREEN + NIR)"

    return evidence


async def process_chat_message(req: ChatMessageRequest) -> Dict[str, Any]:
    """Unified handler for chat messages and actions."""
    message = sanitize_query(req.message, 1000)
    if not message:
        raise HTTPException(status_code=422, detail="Message cannot be empty or only whitespace")

    from sqlalchemy.orm import sessionmaker
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
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

        location = req.location or sess.location
        image_id = req.image_id or sess.image_id
        aoi = req.aoi if req.aoi is not None else sess.aoi_json

        result: Dict[str, Any] = {}
        msg_lower = message.lower().strip()
        action: Optional[Dict[str, Any]] = None

        # -------------------------------------------------------------
        # Action Handler 1: Basemap switching
        # -------------------------------------------------------------
        if task == "basemap_switch":
            is_satellite = "satellite" in msg_lower
            target_basemap = "satellite" if is_satellite else "default"
            answer_text = (
                "Switched map view to high-resolution **Satellite Imagery**." if is_satellite
                else "Switched map view to **Default (OpenStreetMap)**."
            )
            action = {"type": "set_basemap", "payload": {"basemap": target_basemap}}
            result = {
                "success": True,
                "answer_text": answer_text,
                "detected_task": "basemap_switch",
                "action": action,
                "confidence": 1.0,
                "sources": ["satquery_map_controller"],
            }

        # -------------------------------------------------------------
        # Action Handler 2: Coordinates Search (e.g. "Find 11.2189, 78.1674")
        # -------------------------------------------------------------
        elif task == "coordinate_search" or parse_coordinates(message) is not None:
            coords = parse_coordinates(message)
            if coords:
                lat, lon = coords
                geo_res = await geocode_coordinates(lat, lon)
                if geo_res.get("success"):
                    p_name = geo_res.get("place_name")
                    admin = geo_res.get("admin_level") or "Administrative Area"
                    state = geo_res.get("state") or "—"
                    district = geo_res.get("district") or "—"
                    country = geo_res.get("country") or "India"
                    has_b = geo_res.get("has_real_boundary")
                    area_km2 = geo_res.get("area_km2")

                    if has_b and area_km2:
                        b_text = f"Actual administrative polygon retrieved ({area_km2:.2f} km² / {geo_res.get('area_ha', 0):.0f} ha)"
                    else:
                        b_text = "Location found, but an exact administrative boundary is unavailable. You can draw a custom AOI manually."

                    answer_text = (
                        f"### Location Found via Coordinates\n\n"
                        f"- **Place:** {geo_res.get('display_name')}\n"
                        f"- **Administrative Level:** {admin}\n"
                        f"- **District:** {district}\n"
                        f"- **State:** {state}\n"
                        f"- **Country:** {country}\n"
                        f"- **Coordinates:** Latitude {lat:.5f}, Longitude {lon:.5f}\n"
                        f"- **Boundary:** {b_text}\n"
                        f"- **Data Source:** Nominatim (OpenStreetMap)"
                    )
                    action = {"type": "set_location", "payload": geo_res}
                    result = {
                        "success": True,
                        "answer_text": answer_text,
                        "detected_task": "coordinate_search",
                        "action": action,
                        "location_info": geo_res,
                        "confidence": 0.98,
                        "sources": ["Nominatim (OpenStreetMap)"],
                    }
                else:
                    answer_text = f"Could not reverse geocode coordinates ({lat}, {lon}): {geo_res.get('error', 'Location not found')}."
                    result = {"success": False, "answer_text": answer_text, "detected_task": "coordinate_search"}

        # -------------------------------------------------------------
        # Action Handler 3: Boundary Selection (e.g. "Select Namakkal District boundary")
        # -------------------------------------------------------------
        elif task == "boundary_selection":
            # Extract target place
            cand = re.sub(r"^(select|show|use|get)\s+(the\s+)?(actual|real|complete|entire|official)?\s*(administrative\s+)?boundary\s*(of\s+)?", "", message, flags=re.IGNORECASE).strip()
            cand = re.sub(r"\s+(boundary|as\s+my\s+aoi|as\s+aoi|as\s+study\s+area)$", "", cand, flags=re.IGNORECASE).strip()
            loc_to_use = cand if (cand and len(cand) >= 3 and cand.lower() not in {"district", "state", "city", "boundary"}) else (location or "Namakkal District")

            geo_res = await geocode(loc_to_use)
            if geo_res.get("success"):
                if geo_res.get("has_real_boundary"):
                    action = {
                        "type": "set_aoi",
                        "payload": {
                            "geojson": geo_res.get("geometry"),
                            "area_km2": geo_res.get("area_km2"),
                            "location": geo_res,
                        }
                    }
                    answer_text = (
                        f"Selected the **actual administrative boundary** for **{geo_res.get('place_name')}** ({geo_res.get('admin_level')}).\n\n"
                        f"- **Calculated Geodesic Area:** {geo_res.get('area_km2')} km² ({geo_res.get('area_ha'):.0f} hectares / {geo_res.get('area_sqft'):.0f} sq ft)\n"
                        f"- **Boundary Type:** True OSM {geo_res.get('geometry', {}).get('type')} Polygon (No artificial square)\n"
                        f"- **Center Coordinates:** Lat {geo_res.get('lat'):.5f}, Lon {geo_res.get('lon'):.5f}\n"
                        f"- **Active AOI:** Successfully set and synchronized across all pages."
                    )
                else:
                    action = {"type": "set_location", "payload": geo_res}
                    answer_text = (
                        f"Found **{geo_res.get('display_name')}**, but an exact administrative polygon is unavailable. "
                        f"You can use the manual drawing tools (Polygon, Rectangle, Circle) to define a custom study area."
                    )
                result = {
                    "success": True,
                    "answer_text": answer_text,
                    "detected_task": "boundary_selection",
                    "action": action,
                    "location_info": geo_res,
                    "confidence": 0.98,
                    "sources": ["Nominatim (OpenStreetMap)"],
                }

        # -------------------------------------------------------------
        # Action Handler 4: Location Name Search (e.g. "Find Namakkal", "Show Tamil Nadu", "Locate Karur")
        # -------------------------------------------------------------
        elif task == "location_search" or (
            any(msg_lower.startswith(prefix) for prefix in ["find ", "show ", "locate ", "go to ", "zoom to ", "where is ", "select "])
            and len(message.split()) <= 6
            and not any(w in msg_lower for w in ["ndvi", "ndwi", "ndbi", "water", "vegetation", "agriculture", "agri", "crop", "built-up", "built up", "built", "urban", "forest", "canopy", "overall", "change", "image", "chart"])
        ):
            cand = re.sub(r"^(find|show|locate|go\s+to|zoom\s+to|where\s+is|select|use)\s+", "", message, flags=re.IGNORECASE).strip()
            cand = re.sub(r"\s+(as\s+(my\s+)?(aoi|study\s+area|active\s+area)|boundary)$", "", cand, flags=re.IGNORECASE).strip()
            if cand:
                geo_res = await geocode(cand)
                if geo_res.get("success"):
                    p_name = geo_res.get("place_name")
                    admin = geo_res.get("admin_level") or "Administrative Area"
                    state = geo_res.get("state") or "—"
                    district = geo_res.get("district") or "—"
                    country = geo_res.get("country") or "India"
                    has_b = geo_res.get("has_real_boundary")
                    area_km2 = geo_res.get("area_km2")

                    if has_b and area_km2:
                        b_text = f"Actual boundary retrieved ({area_km2:.2f} km² / {geo_res.get('area_ha', 0):.0f} ha)"
                    else:
                        b_text = "Point identified (custom AOI can be drawn manually on the map)"

                    answer_text = (
                        f"### Location Found\n\n"
                        f"- **Place Name:** {p_name}\n"
                        f"- **Administrative Level:** {admin}\n"
                        f"- **District:** {district}\n"
                        f"- **State:** {state}\n"
                        f"- **Country:** {country}\n"
                        f"- **Center Coordinates:** Lat {geo_res.get('lat'):.5f}, Lon {geo_res.get('lon'):.5f}\n"
                        f"- **Boundary:** {b_text}\n"
                        f"- **Data Source:** Nominatim (OpenStreetMap)"
                    )
                    action = {"type": "set_location", "payload": geo_res}
                    result = {
                        "success": True,
                        "answer_text": answer_text,
                        "detected_task": "location_search",
                        "action": action,
                        "location_info": geo_res,
                        "confidence": 0.98,
                        "sources": ["Nominatim (OpenStreetMap)"],
                    }

        # -------------------------------------------------------------
        # Action Handler 5: AOI Control (e.g. "Clear my AOI")
        # -------------------------------------------------------------
        elif task == "aoi_control":
            if "clear" in msg_lower:
                action = {"type": "clear_aoi"}
                answer_text = "Cleared the active Area of Interest (AOI). You can search for a new location or draw a polygon on any map."
            else:
                answer_text = (
                    "You can draw a custom AOI using the Polygon, Rectangle, or Circle controls on any map page, "
                    "or ask me to select the real boundary of any district, city, or state."
                )
            result = {
                "success": True,
                "answer_text": answer_text,
                "detected_task": "aoi_control",
                "action": action,
                "confidence": 1.0,
            }

        # -------------------------------------------------------------
        # Action Handler 6: Image Analysis
        # -------------------------------------------------------------
        elif task == "image_analysis" or (
            image_id and any(w in msg_lower for w in ["analyze this image", "describe this image", "what does this image show", "find vegetation in this image", "find water in this image"])
        ):
            if image_id:
                settings = get_settings()
                candidates = list(settings.UPLOADS_DIR.glob(f"{image_id}.*"))
                if candidates:
                    img_res = await analyze_visual_satellite_image(str(candidates[0]), user_prompt=message)
                    if img_res.get("success"):
                        features_str = "\n".join(f"- {f}" for f in img_res.get("detected_features", []))
                        answer_text = (
                            f"### IMAGE ANALYSIS COMPLETE\n\n"
                            f"**Image Type:** {img_res.get('image_type')}\n"
                            f"**Format:** {img_res.get('format')}\n"
                            f"**Analysis Mode:** {img_res.get('analysis_mode')}\n\n"
                            f"**Detected Features:**\n{features_str}\n\n"
                            f"**Summary:**\n{img_res.get('summary')}\n\n"
                            f"**What was analyzed:** {img_res.get('what_was_analyzed')}\n\n"
                            f"**Evidence:** {img_res.get('evidence')}\n\n"
                            f"**Confidence:** {int(img_res.get('confidence', 0.88)*100)}%\n\n"
                            f"**Limitations:** {img_res.get('limitations')}"
                        )
                        result = {
                            "success": True,
                            "answer_text": answer_text,
                            "detected_task": "image_analysis",
                            "image_analysis": img_res,
                            "confidence": img_res.get("confidence", 0.88),
                            "sources": ["visual_satellite_analyzer"],
                        }
            else:
                answer_text = "Please upload a satellite or aerial image on the Satellite Analysis page to run visual or multispectral analysis."
                result = {"success": True, "answer_text": answer_text, "detected_task": "image_upload_prompt"}

        # -------------------------------------------------------------
        # Action Handler 7: Year / date comparison intents
        # -------------------------------------------------------------
        elif task in ("year_compare", "date_compare", "change_detection") and any(w in msg_lower for w in ["compare", "change between"]):
            years = [int(y) for y in re.findall(r"\b(20\d{2}|19\d{2})\b", message)]
            idx_m = None
            for name in ("ndvi", "ndwi", "ndbi", "evi", "savi"):
                if name in message.lower():
                    idx_m = name
                    break
            loc = location if location and location != "India" else "Namakkal District"
            if len(years) >= 2 and loc:
                from backend.services.satellite_service import compare_scenes_by_years
                from backend.services.geocoding_service import geocode as _geocode
                geo = await _geocode(loc)
                if geo.get("success"):
                    bb = geo.get("bbox")
                    if not bb:
                        lat, lon = float(geo["lat"]), float(geo["lon"])
                        d = 0.05
                        bb = [lon - d, lat - d, lon + d, lat + d]
                    ya, yb = years[0], years[1]
                    cmp = await compare_scenes_by_years(bb, ya, yb, index=idx_m)
                    answer_text = cmp.get("message") or "Comparison finished."
                    if cmp.get("summary_a"):
                        sa, sb = cmp["summary_a"], cmp["summary_b"]
                        answer_text += (
                            f"\n\n- **Year {ya}:** Acquired {sa.get('acquisition_date')}, Cloud {sa.get('cloud_cover_pct')}%, Sensor: {sa.get('satellite')} ({sa.get('collection')})."
                            f"\n- **Year {yb}:** Acquired {sb.get('acquisition_date')}, Cloud {sb.get('cloud_cover_pct')}%, Sensor: {sb.get('satellite')} ({sb.get('collection')})."
                        )
                    result = {
                        "success": cmp.get("success", False),
                        "answer_text": answer_text,
                        "detected_task": "year_compare",
                        "comparison": cmp,
                        "chips": ["year_compare", str(ya), str(yb)] + ([idx_m] if idx_m else []),
                        "sources": ["Microsoft Planetary Computer STAC"],
                    }

        # -------------------------------------------------------------
        # Action Handler 8: Spectral Landcover & Index Actions (e.g. "Show water", "Calculate NDVI", "Show vegetation")
        # -------------------------------------------------------------
        elif task in ("ndwi_analysis", "ndvi_analysis", "ndbi_analysis") or any(w in msg_lower for w in ["show water", "calculate ndwi", "show vegetation", "calculate ndvi", "show agricultural land", "show agriculture", "show built-up", "show built up", "calculate ndbi", "show forest", "show canopy"]):
            cat_key = "water"
            if "ndwi" in msg_lower or "water" in msg_lower:
                cat_key = "water"
                cat_name = "Water Bodies"
                formula = "NDWI = (Green - NIR) / (Green + NIR)"
            elif "ndvi" in msg_lower or "vegetation" in msg_lower or "agri" in msg_lower or "crop" in msg_lower:
                cat_key = "agri"
                cat_name = "Agricultural Land"
                formula = "NDVI = (NIR - Red) / (NIR + Red)"
            elif "ndbi" in msg_lower or "built" in msg_lower or "urban" in msg_lower:
                cat_key = "builtup"
                cat_name = "Built-up Area"
                formula = "NDBI = (SWIR - NIR) / (SWIR + NIR)"
            elif "forest" in msg_lower or "canopy" in msg_lower:
                cat_key = "forest"
                cat_name = "Forest & Canopy"
                formula = "NDVI > 0.50 High Canopy Mask"

            loc_to_use = location or "Namakkal District"
            action = {"type": "select_landcover", "payload": {"category": cat_key}}
            answer_text = (
                f"### {cat_name} Analysis ({formula})\n\n"
                f"- **Active Area:** {loc_to_use}\n"
                f"- **Remote Sensing Method:** `{formula}`\n"
                f"- **Data Stream:** Microsoft Planetary Computer Sentinel-2 multispectral surface reflectance.\n"
                f"- **Action:** Rendered detected {cat_name} layer on Area Overview map in the designated category color."
            )
            result = {
                "success": True,
                "answer_text": answer_text,
                "detected_task": "landcover_analysis",
                "action": action,
                "confidence": 0.95,
                "sources": ["Microsoft Planetary Computer STAC", "SatQuery Spectral Analyzer"],
            }

        # -------------------------------------------------------------
        # General & Analytical Pipeline: KnowledgeEngine RAG + Groq AI + Data Fusion
        # -------------------------------------------------------------
        if not result:
            evidence: Dict[str, Any] = {}
            analysis: Dict[str, Any] = {}

            is_general_science = any(phrase in msg_lower for phrase in [
                "what is", "what does", "how does", "why is", "how is", "explain",
                "what are", "difference between", "how can", "can you tell", "define"
            ]) and not any(loc_word in msg_lower for loc_word in ["in this area", "in namakkal", "here", "selected area", "this region"])

            if not is_general_science and (location or aoi or image_id):
                loc_to_use = location or "Namakkal District"
                analysis = await analyze_query(loc_to_use, message, aoi)
                evidence = _extract_analysis_evidence(analysis, message, loc_to_use, extra_context=req.context)
            else:
                if location:
                    evidence["location"] = location

            image_png: Optional[bytes] = None
            if image_id:
                settings = get_settings()
                candidates = list(settings.UPLOADS_DIR.glob(f"{image_id}.*"))
                if candidates:
                    from backend.ai.raster_chip import render_chip_from_path
                    image_png, _ = render_chip_from_path(candidates[0], render="rgb", max_px=1024)

            vlm_out = await run_vlm(message, image_png, evidence, history=history)

            answer_text = vlm_out.get("answer") or analysis.get("answer_text") or "Analysis completed."
            confidence = vlm_out.get("confidence") or analysis.get("confidence") or 0.9

            result = {
                "success": analysis.get("success", True),
                "answer_text": answer_text,
                "analysis": analysis,
                "detected_task": task,
                "execution_trace": analysis.get("execution_trace", []),
                "metrics": analysis.get("metrics"),
                "confidence": confidence,
                "evidence": evidence,
                "sources": vlm_out.get("sources") or analysis.get("sources") or ["groq_ai", "satquery_knowledge_base"],
                "map_layers": analysis.get("map_layers"),
                "action": action,
            }

        final_answer = result.get("answer_text") or "No answer generated."
        assistant_msg = Message(
            session_id=session_id,
            role="assistant",
            content=final_answer,
            meta_json={
                "task": result.get("detected_task"),
                "confidence": result.get("confidence"),
                "evidence": result.get("evidence"),
                "execution_trace": result.get("execution_trace"),
                "sources": result.get("sources"),
                "action": result.get("action"),
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
            "content": final_answer,
            "task": result.get("detected_task"),
            "confidence": result.get("confidence"),
            "evidence": result.get("evidence"),
            "execution_trace": result.get("execution_trace"),
            "sources": result.get("sources"),
            "action": result.get("action"),
            "success": result.get("success", True),
        }
    except Exception as exc:
        logger.exception("chat message failed: %s", exc)
        return {
            "session_id": req.session_id or "err",
            "role": "assistant",
            "content": f"SatQuery AI encountered an error processing your request: {exc}",
            "task": "error",
            "success": False,
        }
    finally:
        db.close()


@router.post("")
@router.post("/")
async def chat_root(req: ChatMessageRequest):
    """POST /api/chat endpoint."""
    return await process_chat_message(req)


@router.post("/message")
async def chat_message_endpoint(req: ChatMessageRequest):
    """POST /api/chat/message endpoint."""
    return await process_chat_message(req)


@router.get("/knowledge/search")
async def search_knowledge_endpoint(
    q: str = Query(..., min_length=1, description="Query string to search knowledge base"),
    top_k: int = Query(4, ge=1, le=20)
):
    """Direct search endpoint for the remote sensing knowledge base."""
    matches = search_knowledge(q, top_k=top_k)
    return {
        "query": q,
        "results_count": len(matches),
        "matches": matches
    }


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
