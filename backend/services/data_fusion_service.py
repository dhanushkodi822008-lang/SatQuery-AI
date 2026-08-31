"""
Orchestrates multi-source data for a location + query.
Uses real STAC scenes, Open-Meteo, OSM, and optional real COG band processing.
Never fabricates satellite percentages or gauge levels.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import re

from backend.services.geocoding_service import geocode
from backend.services.satellite_service import get_best_optical_scene, get_best_sar_scene
from backend.services.weather_service import get_weather
from backend.services.water_level_service import get_water_level
from backend.services.osm_service import get_water_features
from backend.ai.query_router import route_query
from backend.ai.flood_risk import assess_flood_risk
from backend.ai.change_detection import run_change_detection
from backend.ai.optical_sar import run_optical_sar
from backend.ai.vqa import answer_vqa
from backend.ai.captioning import caption_scene
from backend.ai.grounding import ground_phrase
from backend.ai.landcover import estimate_agriculture
from backend.processing.raster_processing import analyze_optical_aoi, summarize_without_raster
from backend.processing.area_calculation import aoi_area_from_bbox, aoi_area_from_geojson
from backend.utils.logging import logger
from backend.utils.validation import validate_polygon_geojson


async def analyze_query(location_query: str, user_question: str, aoi_geojson: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    trace: List[Dict[str, Any]] = []

    # 1. Geocode
    trace.append({"step": "geocode", "status": "running", "detail": location_query})
    loc = await geocode(location_query)
    if not loc.get("success"):
        return {
            "success": False,
            "error": loc.get("error", "Geocoding failed"),
            "execution_trace": trace + [{"step": "geocode", "status": "failed", "detail": loc}],
        }
    trace.append({
        "step": "geocode",
        "status": "ok",
        "detail": {
            "display_name": loc["display_name"],
            "lat": loc["lat"],
            "lon": loc["lon"],
            "source": loc["source"],
        },
    })

    bbox = loc["bbox"]
    if aoi_geojson is not None:
        validate_polygon_geojson(aoi_geojson)
        from shapely.geometry import shape
        bbox = list(shape(aoi_geojson).bounds)
        aoi_km2 = aoi_area_from_geojson(aoi_geojson)
    else:
        aoi_km2 = loc.get("aoi_area_km2") or aoi_area_from_bbox(bbox)

    # 2. Route
    routing = route_query(user_question)
    trace.append({"step": "route_query", "status": "ok", "detail": {
        "detected_task": routing.get("detected_task"),
        "selected_model": (routing.get("selected_model") or {}).get("name"),
        "model_status": routing.get("model_status"),
    }})
    task = routing["detected_task"]

    # 3. Optical search (common)
    optical = await get_best_optical_scene(bbox)
    trace.append({
        "step": "satellite_optical_search",
        "status": "ok" if optical.get("success") else "no_data",
        "detail": {
            "success": optical.get("success"),
            "scene_id": (optical.get("scene") or {}).get("id"),
            "date": (optical.get("scene") or {}).get("acquisition_date"),
            "cloud_cover_pct": (optical.get("scene") or {}).get("cloud_cover_pct"),
            "error": optical.get("error"),
        },
    })

    answer: Dict[str, Any] = {
        "success": True,
        "location": loc,
        "question": user_question,
        "detected_task": task,
        "routing": routing,
        "data_status": "PARTIAL_DATA",
        "freshness": {},
        "answer_text": "",
        "metrics": {},
        "evidence": [],
        "map_layers": {"aoi": bbox, "manual_aoi": aoi_geojson},
        "sources": [],
        "confidence": None,
        "execution_trace": trace,
        "limitations": [],
        "satellite_optical": optical if optical.get("success") else {"success": False, "error": optical.get("error")},
    }

    # ---- Task handlers ----

    if task == "weather":
        weather = await get_weather(loc["lat"], loc["lon"])
        trace.append({"step": "weather", "status": "ok" if weather.get("success") else "failed"})
        answer["weather"] = weather
        answer["freshness"]["weather"] = weather.get("updated_at")
        answer["sources"].append({"name": weather.get("source"), "url": weather.get("source_url")})
        if weather.get("success"):
            c = weather["current"]
            answer["answer_text"] = (
                f"Current conditions near {loc['display_name']}: "
                f"{c.get('temperature_c')}°C, humidity {c.get('humidity_pct')}%, "
                f"{c.get('weather_description')}, wind {c.get('wind_speed_kmh')} km/h. "
                f"Last 24h rainfall: {(weather.get('rainfall') or {}).get('last_24h_mm')} mm. "
                f"3-day forecast precip: {(weather.get('rainfall') or {}).get('forecast_next_3d_mm')} mm. "
                f"Source: {weather['source']} (observed {c.get('observed_at')}). "
                f"Note: air temperature at 2 m — not satellite land-surface temperature."
            )
            answer["metrics"] = {
                "temperature_c": c.get("temperature_c"),
                "humidity_pct": c.get("humidity_pct"),
                "precip_24h_mm": (weather.get("rainfall") or {}).get("last_24h_mm"),
                "forecast_3d_mm": (weather.get("rainfall") or {}).get("forecast_next_3d_mm"),
            }
            answer["evidence"].append(f"Weather source: {weather.get('source')} @ {weather.get('updated_at')}")
            answer["data_status"] = "DATA_CONNECTED"
            answer["confidence"] = 0.9
        else:
            answer["answer_text"] = f"Real data unavailable for this request: {weather.get('error')}"

    elif task == "water_level":
        wl = await get_water_level(loc["lat"], loc["lon"], loc.get("display_name", ""))
        answer["water_level"] = wl
        answer["answer_text"] = wl.get("message", "Current gauge water-level observation unavailable.")
        answer["limitations"].append(wl.get("note"))
        answer["sources"].append({"name": "Water level service", "detail": wl.get("reason")})
        answer["evidence"].append(wl.get("reason") or "No gauge feed connected")

    elif task == "flood_risk":
        weather = await get_weather(loc["lat"], loc["lon"])
        wl = await get_water_level(loc["lat"], loc["lon"], loc.get("display_name", ""))
        water_extent = None
        if optical.get("success"):
            try:
                water_extent = analyze_optical_aoi(optical["scene"], bbox, aoi_km2, ["ndwi"], aoi_geojson)
                trace.append({"step": "ndwi_for_flood", "status": "ok" if water_extent.get("mode") == "RASTER" else "metadata"})
            except Exception as e:
                logger.warning(f"NDWI for flood risk failed: {e}")
                water_extent = summarize_without_raster(optical["scene"], aoi_km2, "water")
        risk = assess_flood_risk(weather, water_extent, wl, loc.get("display_name", ""))
        answer["flood_risk"] = risk
        answer["weather"] = weather
        answer["water_extent"] = water_extent
        answer["answer_text"] = (
            f"Flood-risk indicator: {risk['flood_risk']} "
            f"(score {risk['risk_indicator_score']}/100). "
            f"{risk['disclaimer']} Evidence: " + "; ".join(risk["evidence"])
        )
        answer["metrics"] = {"risk_score": risk["risk_indicator_score"], "level": risk["flood_risk"]}
        answer["evidence"] = risk["evidence"]
        answer["data_status"] = "PARTIAL_DATA" if weather.get("success") else "NO_CURRENT_DATA"
        answer["confidence"] = 0.55
        answer["sources"].append({"name": weather.get("source") if weather else None})

    elif task == "water_analysis":
        osm = await get_water_features(bbox)
        trace.append({"step": "osm_water", "status": "ok" if osm.get("success") else "failed",
                      "detail": {"feature_count": osm.get("feature_count")}})
        answer["osm_water"] = osm
        answer["map_layers"]["osm_water_features"] = osm.get("features", [])

        if optical.get("success"):
            scene = optical["scene"]
            try:
                raster = analyze_optical_aoi(scene, bbox, aoi_km2, ["ndwi"], aoi_geojson)
            except Exception as e:
                logger.warning(f"Water raster analysis failed: {e}")
                raster = summarize_without_raster(scene, aoi_km2, "water")
                raster["fetch_error"] = str(e)

            answer["satellite_water"] = raster
            trace.append({
                "step": "ndwi_processing",
                "status": "ok" if raster.get("mode") == "RASTER" else "metadata_only",
                "detail": {"mode": raster.get("mode"), "error": raster.get("fetch_error")},
            })

            names = [f["name"] for f in osm.get("features", [])[:10] if f.get("name")]
            q = (raster.get("quantitative_result") or {}).get("water")

            if raster.get("mode") == "RASTER" and q:
                water_message = (
                    "No water detected in the analyzed pixels."
                    if not q.get("fraction_of_valid_pixels")
                    else (
                        f"Satellite-derived water extent: {q.get('area_km2')} km² "
                        f"(~{q.get('pct_of_aoi_approx')}% of valid pixels in AOI)."
                    )
                )
                answer["answer_text"] = (
                    f"Water analysis for {loc['display_name']}.\n"
                    f"{water_message}\n"
                    f"Observation: {scene.get('acquisition_date')} | "
                    f"{scene.get('satellite')} / {scene.get('sensor')} | "
                    f"cloud {scene.get('cloud_cover_pct')}% | {scene.get('resolution_m')} m.\n"
                    f"Method: {q.get('method')}.\n"
                    f"Mapped OSM water names: {', '.join(names) if names else 'none named in AOI'}.\n"
                    f"IMPORTANT: This is satellite water EXTENT (area), not gauge water LEVEL (metres)."
                )
                answer["metrics"] = {
                    "water_area_km2": q.get("area_km2"),
                    "water_pct_approx": q.get("pct_of_aoi_approx"),
                    "aoi_km2": aoi_km2,
                    "observation_date": scene.get("acquisition_date"),
                }
                answer["data_status"] = "DATA_CONNECTED"
                answer["confidence"] = 0.75
                if raster.get("map_points", {}).get("water"):
                    answer["map_layers"]["ndwi_water_points"] = raster["map_points"]["water"]
                if raster.get("map_geojson", {}).get("water", {}).get("features"):
                    answer["map_layers"]["ndwi_water_geojson"] = raster["map_geojson"]["water"]
            else:
                answer["answer_text"] = (
                    f"I couldn't analyze satellite pixels for {loc['display_name']} because "
                    f"the required optical bands were unavailable. No water result was generated."
                )
                answer["technical_details"] = {
                    "satellite": scene.get("satellite"),
                    "acquisition_date": scene.get("acquisition_date"),
                    "cloud_cover_pct": scene.get("cloud_cover_pct"),
                    "source": "Microsoft Planetary Computer / Copernicus",
                    "error": raster.get("fetch_error") or raster.get("message") or "band fetch unavailable",
                    "bands_required": ["green", "nir"],
                    "fetch_mode": raster.get("fetch_mode"),
                    "fetch_details": raster.get("fetch_details"),
                }
                answer["data_status"] = "PARTIAL_DATA"
                answer["confidence"] = 0.6

            answer["freshness"]["satellite"] = scene.get("acquisition_date")
            answer["sources"].extend([
                {"name": "Microsoft Planetary Computer STAC", "collection": scene.get("collection")},
                {"name": osm.get("source")},
            ])
            answer["evidence"].append(
                f"Optical scene {scene.get('id')} @ {scene.get('acquisition_date')}"
            )
        else:
            answer["answer_text"] = (
                f"Real data unavailable for optical water analysis. "
                f"Reason: {optical.get('error') or optical.get('reason')}. "
                f"OSM named features found: {osm.get('feature_count', 0)}."
            )
            answer["data_status"] = "NO_CURRENT_DATA"

    elif task in ("agriculture", "vegetation"):
        if optical.get("success"):
            scene = optical["scene"]
            try:
                raster = analyze_optical_aoi(scene, bbox, aoi_km2, ["ndvi"], aoi_geojson, vegetation_threshold=0.25 if task == "agriculture" else 0.3)
            except Exception as e:
                raster = summarize_without_raster(scene, aoi_km2, "vegetation")
                raster["fetch_error"] = str(e)
            answer["vegetation"] = raster
            veg = (raster.get("quantitative_result") or {}).get("vegetation_indicated")
            if raster.get("mode") == "RASTER" and veg:
                category_label = "Agriculture/vegetation" if task == "agriculture" else "Forest / Vegetation"
                detection_message = (
                    f"No {category_label} detected in the selected area."
                    if not veg.get("fraction")
                    else f"Vegetation-indicated fraction: ~{veg.get('pct_approx')}% of valid pixels."
                )
                answer["answer_text"] = (
                    f"Vegetation indication for {loc['display_name']}.\n"
                    f"Mean NDVI: {veg.get('mean_ndvi')}. "
                    f"{detection_message}\n"
                    f"Observation: {scene.get('acquisition_date')} | {scene.get('satellite')}.\n"
                    f"Method: {veg.get('method')}.\n"
                    f"NOTE: NDVI indicates green vegetation vigor — it is NOT a direct agricultural land-use classifier. "
                    f"Crops, forests, and plantations can all show high NDVI."
                )
                answer["metrics"] = {
                    "mean_ndvi": veg.get("mean_ndvi"),
                    "vegetation_pct_approx": veg.get("pct_approx"),
                    "observation_date": scene.get("acquisition_date"),
                }
                answer["data_status"] = "DATA_CONNECTED"
                answer["confidence"] = 0.7
                if raster.get("map_geojson", {}).get("vegetation", {}).get("features"):
                    answer["map_layers"]["vegetation_geojson"] = raster["map_geojson"]["vegetation"]
            else:
                agri = estimate_agriculture({"location": loc, "optical": optical})
                answer["agriculture"] = agri
                answer["answer_text"] = agri["message"]
                answer["data_status"] = "PARTIAL_DATA"
            answer["freshness"]["satellite"] = scene.get("acquisition_date")
            answer["sources"].append({"name": "Microsoft Planetary Computer STAC"})
            answer["limitations"].append(
                "Agricultural land-use classification requires a trained land-cover model or official LULC dataset."
            )
        else:
            answer["answer_text"] = f"Real data unavailable: {optical.get('error')}"
            answer["data_status"] = "NO_CURRENT_DATA"

    elif task == "builtup":
        if optical.get("success"):
            scene = optical["scene"]
            try:
                raster = analyze_optical_aoi(scene, bbox, aoi_km2, ["ndbi"], aoi_geojson)
            except Exception as e:
                raster = summarize_without_raster(scene, aoi_km2, "builtup")
                raster["fetch_error"] = str(e)
            answer["builtup"] = raster
            b = (raster.get("quantitative_result") or {}).get("builtup_indicated")
            if raster.get("mode") == "RASTER" and b:
                builtup_message = (
                    "No Built-up detected in the selected area."
                    if not b.get("fraction")
                    else (
                        f"NDBI-indicated fraction: ~{b.get('pct_approx')}% of valid pixels "
                        f"(~{b.get('area_km2_approx')} km² at analysis resolution)."
                    )
                )
                answer["answer_text"] = (
                    f"Built-up indication for {loc['display_name']}.\n"
                    f"{builtup_message}\n"
                    f"Observation: {scene.get('acquisition_date')} | {scene.get('satellite')}.\n"
                    f"Method: {b.get('method')}.\n"
                    f"NOTE: NDBI responds to built-up and bare soil; not every bright pixel is a building."
                )
                answer["metrics"] = {
                    "builtup_pct_approx": b.get("pct_approx"),
                    "builtup_km2_approx": b.get("area_km2_approx"),
                    "observation_date": scene.get("acquisition_date"),
                }
                answer["data_status"] = "DATA_CONNECTED"
                answer["confidence"] = 0.65
                if raster.get("map_points", {}).get("builtup"):
                    answer["map_layers"]["ndbi_points"] = raster["map_points"]["builtup"]
                if raster.get("map_geojson", {}).get("builtup", {}).get("features"):
                    answer["map_layers"]["ndbi_geojson"] = raster["map_geojson"]["builtup"]
            else:
                answer["answer_text"] = (
                    f"Built-up analysis: scene {scene.get('acquisition_date')} found. "
                    f"NDBI raster not computed ({raster.get('fetch_error') or 'band fetch unavailable'}). "
                    f"No percentage fabricated."
                )
                answer["data_status"] = "PARTIAL_DATA"
            answer["freshness"]["satellite"] = scene.get("acquisition_date")
            answer["sources"].append({"name": "Microsoft Planetary Computer STAC"})
        else:
            answer["answer_text"] = f"Real data unavailable: {optical.get('error')}"

    elif task == "change_detection":
        years = re.findall(r"20\d{2}", user_question)
        yb, ya = 2024, 2025
        if len(years) >= 2:
            yb, ya = int(years[0]), int(years[1])
        elif len(years) == 1:
            ya = int(years[0])
            yb = ya - 1
        change = await run_change_detection(bbox, yb, ya, aoi_km2=aoi_km2)
        answer["change"] = change
        trace.append({"step": "change_detection", "status": "ok" if change.get("success") else "failed"})
        if change.get("success"):
            answer["answer_text"] = change.get("summary_text") or (
                f"Change analysis {yb}→{ya} for {loc['display_name']}. "
                f"Before: {(change.get('before_scene') or {}).get('acquisition_date', 'none')}. "
                f"After: {(change.get('after_scene') or {}).get('acquisition_date', 'none')}. "
                f"{change.get('message')}"
            )
            answer["metrics"] = change.get("metrics") or {}
            answer["data_status"] = "PARTIAL_DATA" if change.get("quantitative_change") else "PARTIAL_DATA"
            if change.get("mode") == "RASTER":
                answer["data_status"] = "DATA_CONNECTED"
            answer["sources"].append({"name": change.get("before_source") or "Planetary Computer STAC"})
            answer["evidence"].append(f"Years {yb}–{ya}; sensors matched where possible")
        else:
            answer["answer_text"] = change.get("error") or "Real data unavailable for change detection"
            answer["data_status"] = "NO_CURRENT_DATA"

    elif task == "optical_sar":
        fusion = await run_optical_sar(bbox, aoi_km2=aoi_km2)
        answer["optical_sar"] = fusion
        trace.append({"step": "optical_sar", "status": "ok" if fusion.get("success") else "failed"})
        answer["answer_text"] = fusion.get("summary_text") or (
            f"Optical + SAR for {loc['display_name']}. {fusion.get('interpretation')}. "
            f"{fusion.get('fusion_method')}"
        )
        answer["metrics"] = fusion.get("metrics") or {}
        answer["data_status"] = "DATA_CONNECTED" if fusion.get("mode") == "RASTER" else (
            "PARTIAL_DATA" if fusion.get("success") else "NO_CURRENT_DATA"
        )
        answer["sources"].append({"name": "Microsoft Planetary Computer STAC"})
        if fusion.get("map_layers"):
            answer["map_layers"].update(fusion["map_layers"])

    elif task == "captioning":
        ctx = {"scene": optical.get("scene") if optical.get("success") else None}
        cap = await caption_scene(ctx)
        answer["caption"] = cap
        answer["answer_text"] = cap["caption"]
        answer["sources"].append({"name": "Metadata caption (VLM checkpoint not installed)"})

    elif task == "grounding":
        g = await ground_phrase(user_question, {"location": loc, "aoi": aoi_geojson, "image_id": None})
        # If water grounding requested, try NDWI mask points
        if optical.get("success") and re.search(r"water", user_question, re.I):
            try:
                raster = analyze_optical_aoi(optical["scene"], bbox, aoi_km2, ["ndwi"], aoi_geojson)
                if raster.get("map_points", {}).get("water"):
                    answer["map_layers"]["ndwi_water_points"] = raster["map_points"]["water"]
                if raster.get("map_geojson", {}).get("water", {}).get("features"):
                    answer["map_layers"]["ndwi_water_geojson"] = raster["map_geojson"]["water"]
                    g["message"] += (
                        f" Spatial evidence: {len(raster['map_points']['water'])} sample water pixels "
                        f"from NDWI over AOI (observation {optical['scene'].get('acquisition_date')})."
                    )
                    g["status"] = "PARTIAL_SPATIAL"
            except Exception:
                pass
        answer["grounding"] = g
        answer["answer_text"] = g["message"]

    else:
        # VQA / default — honest MODEL_UNAVAILABLE if no checkpoint
        ctx = {
            "display_name": loc["display_name"],
            "latest_optical_date": (optical.get("scene") or {}).get("acquisition_date"),
            "scene": optical.get("scene") if optical.get("success") else None,
            "aoi": aoi_geojson,
            "analysis_area_km2": aoi_km2,
        }
        vqa = await answer_vqa(user_question, ctx)
        answer["vqa"] = vqa
        answer["answer_text"] = vqa["answer"]
        if optical.get("success"):
            answer["freshness"]["satellite"] = optical["scene"].get("acquisition_date")
            answer["data_status"] = "PARTIAL_DATA"
            answer["sources"].append({"name": "Microsoft Planetary Computer STAC"})

    answer["execution_trace"] = trace
    return answer
