"""
General remote-sensing knowledge answers for SatQuery AI chat.
Scientific explanations only — never invents measurements or scenes.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

KNOWLEDGE: List[Dict[str, Any]] = [
    {
        "id": "ndvi",
        "triggers": [r"\bwhat\s+is\s+ndvi\b", r"\bndvi\s+(mean|definition|explain|measure)", r"\bwhy\s+is\s+ndvi", r"\bhigh\s+ndvi", r"\bndvi\s+useful"],
        "title": "NDVI",
        "answer": (
            "NDVI (Normalized Difference Vegetation Index) measures vegetation greenness and vigor.\n"
            "Formula: (NIR − Red) / (NIR + Red). Values typically range from −1 to +1.\n"
            "• High NDVI (≈ 0.6–0.9): dense healthy vegetation\n"
            "• Moderate (≈ 0.2–0.5): sparse vegetation / crops mid-season\n"
            "• Low / negative: water, bare soil, built-up, clouds\n"
            "Sentinel-2 and Landsat both support NDVI. This is a scientific definition only — "
            "ask for analysis on a location/AOI to get real measured values from imagery."
        ),
        "chips": ["NDVI", "NIR", "Red", "vegetation"],
    },
    {
        "id": "ndwi",
        "triggers": [r"\bwhat\s+is\s+ndwi\b", r"\bndwi\s+(mean|definition|explain|measure)", r"\bwater\s+index", r"\bmonitor\s+water", r"\bindex.*water"],
        "title": "NDWI",
        "answer": (
            "NDWI (Normalized Difference Water Index) highlights open water and moisture.\n"
            "Common form: (Green − NIR) / (Green + NIR) (McFeeters).\n"
            "High positive NDWI indicates water; vegetation and soil tend toward lower values.\n"
            "Useful for lakes, rivers, floods, and water-body mapping. "
            "For real water extent on your AOI, ask e.g. “Show water bodies in this area.”"
        ),
        "chips": ["NDWI", "Green", "NIR", "water"],
    },
    {
        "id": "ndbi",
        "triggers": [r"\bwhat\s+is\s+ndbi\b", r"\bndbi\b", r"\bbuilt-?up\s+index", r"\burban\s+index", r"\bdetect\s+buildings"],
        "title": "NDBI",
        "answer": (
            "NDBI (Normalized Difference Built-up Index) emphasizes built-up / urban areas.\n"
            "Formula: (SWIR − NIR) / (SWIR + NIR).\n"
            "Higher NDBI often corresponds to buildings and impervious surfaces; vegetation is lower.\n"
            "Requires shortwave infrared (SWIR) and near-infrared bands (e.g. Landsat, Sentinel-2)."
        ),
        "chips": ["NDBI", "SWIR", "NIR", "urban"],
    },
    {
        "id": "evi",
        "triggers": [r"\bwhat\s+is\s+evi\b", r"\bevi\b"],
        "title": "EVI",
        "answer": (
            "EVI (Enhanced Vegetation Index) is similar to NDVI but more resistant to atmospheric "
            "and canopy background effects, and better in high-biomass areas.\n"
            "It uses Blue, Red, and NIR bands. Use when NDVI saturates over dense forest."
        ),
        "chips": ["EVI", "vegetation"],
    },
    {
        "id": "savi",
        "triggers": [r"\bwhat\s+is\s+savi\b", r"\bsavi\b"],
        "title": "SAVI",
        "answer": (
            "SAVI (Soil-Adjusted Vegetation Index) reduces soil brightness influence on vegetation signals.\n"
            "Useful in sparse vegetation / arid regions. It includes a soil-brightness correction factor L (often 0.5)."
        ),
        "chips": ["SAVI", "soil", "vegetation"],
    },
    {
        "id": "sentinel2",
        "triggers": [r"\bwhat\s+is\s+sentinel-?2\b", r"\bsentinel-?2\b", r"\bbest.*vegetation", r"\boptical\s+satellite"],
        "title": "Sentinel-2",
        "answer": (
            "Sentinel-2 (ESA Copernicus) is an optical satellite mission with 10–20–60 m bands "
            "and ~5-day revisit (two satellites). Excellent for vegetation (NDVI), water (NDWI), "
            "and land cover. SatQuery searches Sentinel-2 L2A via Microsoft Planetary Computer STAC."
        ),
        "chips": ["Sentinel-2", "optical", "10m"],
    },
    {
        "id": "sentinel1",
        "triggers": [r"\bwhat\s+is\s+sentinel-?1\b", r"\bsentinel-?1\b", r"\bwhat\s+is\s+sar\b", r"\bsar\b", r"\bradar"],
        "title": "Sentinel-1 / SAR",
        "answer": (
            "Sentinel-1 provides C-band Synthetic Aperture Radar (SAR). It works day/night and through clouds.\n"
            "Useful for flood mapping, ship detection, deformation, and all-weather monitoring. "
            "SAR is not optical RGB; backscatter differs from NDVI-style indices."
        ),
        "chips": ["Sentinel-1", "SAR", "radar"],
    },
    {
        "id": "landsat",
        "triggers": [r"\bwhat\s+is\s+landsat\b", r"\blandsat\b"],
        "title": "Landsat",
        "answer": (
            "Landsat (USGS/NASA) is a long-running optical mission (~30 m, ~16-day revisit). "
            "Ideal for multi-decade change detection. SatQuery uses Landsat Collection 2 Level-2 via Planetary Computer."
        ),
        "chips": ["Landsat", "30m", "historical"],
    },
    {
        "id": "cloud",
        "triggers": [r"\bcloud\s+cover\b", r"\bwhy.*cloud", r"\bwhat\s+does\s+cloud"],
        "title": "Cloud cover",
        "answer": (
            "Cloud cover is the fraction of a scene obscured by clouds. Optical indices (NDVI/NDWI) "
            "are unreliable under thick cloud. Prefer low cloud-cover scenes; SAR (Sentinel-1) is cloud-independent."
        ),
        "chips": ["cloud cover", "optical", "SAR"],
    },
    {
        "id": "resolution",
        "triggers": [r"\bspatial\s+resolution\b", r"\btemporal\s+resolution\b", r"\bbetter\s+resolution\b", r"\bwhich\s+satellite.*resolution"],
        "title": "Resolution",
        "answer": (
            "Spatial resolution: ground pixel size (Sentinel-2 often 10 m; Landsat ~30 m).\n"
            "Temporal resolution: how often the sensor revisits (Sentinel-2 ~5 days; Landsat ~16 days).\n"
            "Spectral resolution: number/width of bands. Higher spatial resolution is not always better "
            "for regional monitoring — coverage and revisit also matter."
        ),
        "chips": ["spatial resolution", "temporal resolution"],
    },
    {
        "id": "bands",
        "triggers": [r"\bbands?\s+used\s+for\s+ndvi", r"\bbands?\s+for\s+ndwi", r"\bspectral\s+bands\b", r"\bwhat\s+are\s+spectral"],
        "title": "Bands for indices",
        "answer": (
            "• NDVI: Red + NIR\n"
            "• NDWI (McFeeters): Green + NIR\n"
            "• NDBI: SWIR + NIR\n"
            "• EVI: Blue + Red + NIR\n"
            "RGB true color uses Red, Green, Blue. False-color composites often use NIR-Red-Green."
        ),
        "chips": ["bands", "NDVI", "NDWI", "NDBI"],
    },
    {
        "id": "flood",
        "triggers": [r"\bflood\b", r"\binundation\b", r"\bflood-?affected"],
        "title": "Flood monitoring",
        "answer": (
            "Flood mapping often combines SAR (Sentinel-1, all-weather) with optical water indices (NDWI) "
            "when clouds allow. Rainfall from weather APIs adds context. SatQuery can report flood-risk "
            "indicators from rainfall + water extent availability — not official warnings."
        ),
        "chips": ["flood", "SAR", "NDWI"],
    },
    {
        "id": "agriculture",
        "triggers": [r"\bagricultur", r"\bcrop\b", r"\bfarmland"],
        "title": "Agriculture monitoring",
        "answer": (
            "NDVI/EVI time series track crop growth and stress. Sentinel-2 is widely used for field-scale "
            "monitoring. Ask for vegetation/agriculture analysis on your AOI for real values from imagery."
        ),
        "chips": ["agriculture", "NDVI", "Sentinel-2"],
    },
    {
        "id": "compare_howto_rs",
        "triggers": [r"\bwhich\s+index\s+(for|should).*urban", r"\bwhich\s+index.*water", r"\bwhich\s+index.*vegetation"],
        "title": "Choosing an index",
        "answer": (
            "• Vegetation / crops / forest → NDVI or EVI\n"
            "• Open water / floods → NDWI\n"
            "• Built-up / urban → NDBI\n"
            "• Sparse vegetation / soil background → SAVI\n"
            "Then run analysis or year/date comparison on your AOI for measured values."
        ),
        "chips": ["NDVI", "NDWI", "NDBI", "EVI", "SAVI"],
    },
]


def match_knowledge(query: str) -> Optional[Dict[str, Any]]:
    q = (query or "").strip().lower()
    if not q:
        return None
    best: Optional[Tuple[int, Dict[str, Any]]] = None
    for item in KNOWLEDGE:
        score = 0
        for pat in item["triggers"]:
            if re.search(pat, q, re.IGNORECASE):
                score += 2
        if score <= 0:
            continue
        if best is None or score > best[0]:
            best = (score, item)
    if not best or best[0] < 2:
        return None
    item = best[1]
    return {
        "success": True,
        "task": "remote_sensing_question",
        "answer": item["answer"],
        "title": item["title"],
        "knowledge_id": item["id"],
        "evidence": {"source": "SatQuery RS knowledge", "id": item["id"]},
        "chips": item.get("chips") or [],
        "sources": ["Remote sensing reference (in-app)"],
        "confidence": 0.9,
    }
