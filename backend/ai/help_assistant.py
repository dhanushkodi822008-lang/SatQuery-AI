"""
SatQuery AI — Help / How-to assistant.

Answers questions about *using the app itself* (AOI, satellite search, indices,
upload, change detection, reports, alerts, workspace). Grounded only in the
real UI labels, routes, and README workflow. Never invents satellite numbers.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# High-quality FAQ pairs (keyword triggers → answer + evidence chips)
# Keep small (8–12) and accurate to the current product.
FAQ: List[Dict[str, Any]] = [
    {
        "id": "aoi",
        "triggers": [
            r"\b(how|where).*(select|draw|create|make|set).*(aoi|area|region|bbox|bounding)",
            r"\bdraw\s+(an?\s+)?(aoi|area)",
            r"\bselect\s+(an?\s+)?(aoi|area)",
            r"\bmanual\s+aoi",
            r"\bfinish\s+area",
            r"\barea\s+selection",
        ],
        "title": "Select / draw AOI",
        "answer": (
            "How to select or draw an Area of Interest (AOI) in SatQuery AI:\n\n"
            "1. On the main Analysis page, find the map in the centre.\n"
            "2. Click the **Select Area** (🖊️) button above the map.\n"
            "3. Click on the map to place vertices of your polygon. Add at least 3 points.\n"
            "4. Click **Finish** (✅) when done. The AOI polygon appears on the map and the area (km²) is shown.\n"
            "5. Use **Clear Area** (🗑️) to remove it, or **Cancel** while drawing.\n\n"
            "You can also type a place name in the Location search box and press Go — the app geocodes it "
            "(Nominatim) and builds a default AOI around the result.\n\n"
            "The active AOI is used by satellite search, index calculation, chat, change comparison, "
            "and reports. Keep it under the configured max area limit (see Settings / status)."
        ),
        "chips": ["AOI", "Select Area", "map", "Nominatim"],
    },
    {
        "id": "satellite_search",
        "triggers": [
            r"\b(how|where).*(search|find|get).*(satellite|scene|imagery|sentinel|landsat|stac)",
            r"\bsatellite\s+(search|imagery|scenes?)",
            r"\bfind\s+(a\s+)?scene",
            r"\bplanetary\s+computer",
        ],
        "title": "Search satellite imagery",
        "answer": (
            "How to search for satellite imagery:\n\n"
            "1. Set a location (search box) or draw an AOI on the map.\n"
            "2. Ask a natural-language question that implies imagery, e.g. “Show water bodies in this area” "
            "or use the **Water bodies** / **Optical + SAR** chips, then click **Send**.\n"
            "3. The backend queries Microsoft Planetary Computer STAC (Sentinel-2 L2A, Landsat C2 L2, "
            "Sentinel-1 RTC). Results show real acquisition dates, cloud cover, and collection names.\n"
            "4. Only scenes that actually exist for your AOI and date window are returned — the app never "
            "invents a scene.\n\n"
            "If no scene is found, widen the date range or accept higher cloud cover. Same-day “live” "
            "satellite is not available; the UI shows the **latest available** date."
        ),
        "chips": ["STAC", "Planetary Computer", "Sentinel-2", "Landsat", "AOI"],
    },
    {
        "id": "indices",
        "triggers": [
            r"\b(how|where).*(calculate|compute|run|get).*(ndvi|ndwi|ndbi|index|indices)",
            r"\bndvi\b",
            r"\bndwi\b",
            r"\bndbi\b",
            r"\bspectral\s+index",
            r"\bland\s*cover",
        ],
        "title": "NDVI / NDWI / NDBI / Land Cover",
        "answer": (
            "How to calculate spectral indices and land cover:\n\n"
            "**From location / AOI (catalog path)**\n"
            "1. Select location or draw AOI.\n"
            "2. Ask e.g. “What is the NDVI / water extent (NDWI) / built-up (NDBI) in this area?” "
            "or use chips such as Water bodies / Agriculture.\n"
            "3. When COG bands are reachable, the backend computes real windowed NDVI, NDWI, or NDBI "
            "and reports metrics with source + date.\n\n"
            "**From an uploaded GeoTIFF**\n"
            "1. Upload a multi-band GeoTIFF (see “How to upload”).\n"
            "2. In **Land Use / Land Cover**, pick a category: Water, Agriculture, Forest / Vegetation, or Built-up.\n"
            "3. Click **Analyze**. Required bands:\n"
            "   • Water → green + NIR (NDWI)\n"
            "   • Agriculture / Forest → red + NIR (NDVI)\n"
            "   • Built-up → SWIR + NIR (NDBI)\n"
            "4. Results appear in the summary panel and as a bounded map overlay.\n\n"
            "If bands or CRS are missing, the API returns a clear scientific reason — it does **not** invent percentages."
        ),
        "chips": ["NDVI", "NDWI", "NDBI", "Land Cover", "GeoTIFF", "Analyze"],
    },
    {
        "id": "upload",
        "triggers": [
            r"\b(how|where).*(upload|import).*(geotiff|tiff|image|raster)",
            r"\bupload\s+(a\s+)?(geo)?tiff",
            r"\buploaded\s+image",
            r"\bimage\s+upload",
        ],
        "title": "Upload GeoTIFF and analyze",
        "answer": (
            "How to upload a GeoTIFF and analyze it:\n\n"
            "1. In the left sidebar, open **Upload Satellite Image**.\n"
            "2. Choose a `.tif` / `.tiff` (or PNG/JPEG for non-geo preview). Prefer multi-band GeoTIFFs with CRS.\n"
            "3. Click **Upload Satellite Image**. On success you get an `image_id` and metadata card.\n"
            "4. Previews: open `/api/images/{image_id}/preview.png?render=rgb|ndvi|ndwi|ndbi` in the browser "
            "(or use the UI when available).\n"
            "5. Run **Land Use / Land Cover → Analyze** for the category you need, or ask in chat "
            "(e.g. “show me where the water is”) — grounding returns GeoJSON + area km² when possible.\n\n"
            "Detection is limited to the uploaded raster’s own bounds and bands. Missing bands → honest error, no fake results."
        ),
        "chips": ["Upload", "GeoTIFF", "image_id", "preview", "Land Cover"],
    },
    {
        "id": "change",
        "triggers": [
            r"\b(how|where).*(change|compare|comparison|bi-?temporal|date\s*[ab])",
            r"\bchange\s+detection",
            r"\bcompare\s+(images|dates|scenes)",
            r"\bdate\s*[ab]\b",
            r"\bbefore\s+and\s+after",
        ],
        "title": "Change detection / comparison",
        "answer": (
            "How to run change detection / comparison:\n\n"
            "**A. Upload-based (two GeoTIFFs)**\n"
            "1. In the **Compare Images** section, choose Before and After files.\n"
            "2. Click **Compare**. Both must be georeferenced GeoTIFFs with compatible CRS/overlap "
            "for geographic change; otherwise the API refuses to claim geographic change.\n\n"
            "**B. Date-based satellite comparison (specific dates)**\n"
            "1. Set location or AOI (shared workspace).\n"
            "2. Enter **Date A** and **Date B** (date pickers or type YYYY-MM-DD).\n"
            "3. Click **Compare dates**. The backend searches Planetary Computer STAC for the best "
            "available scene near each date (same collections when possible).\n"
            "4. Metadata (actual acquisition date, cloud cover, source) is shown for both scenes. "
            "Optional index difference (e.g. NDWI change) when bands are available.\n"
            "5. If no scene exists for a date, the UI reports that honestly — no fake imagery.\n\n"
            "Natural-language: you can also ask “What changed between 2024 and 2025?” in chat."
        ),
        "chips": ["Compare Images", "Date A", "Date B", "STAC", "change"],
    },
    {
        "id": "reports",
        "triggers": [
            r"\b(how|where).*(download|generate|export|get).*(report|pdf|zip)",
            r"\breport\b",
            r"\bexport\b",
        ],
        "title": "Download reports",
        "answer": (
            "How to download reports:\n\n"
            "1. Run an analysis first (location + question, or dashboard overview).\n"
            "2. Click the **Report** button near the chat / answer panel. A plain-text report is generated "
            "from the last analysis (location, question, metrics, sources, execution trace) and downloads "
            "as a `.txt` file.\n"
            "3. On the **Area Overview** dashboard (`/dashboard`), you can also use single-folder ZIP export "
            "(`POST /api/dashboard/export/zip`) which packs report + CSVs + GeoJSON + metadata under "
            "`<district>_<date>/`.\n\n"
            "Reports only contain real values returned by the analysis — they do not invent numbers."
        ),
        "chips": ["Report", "ZIP export", "dashboard"],
    },
    {
        "id": "alerts",
        "triggers": [
            r"\b(how|where).*(alert|monitor|notification|email|sms|twilio|smtp)",
            r"\bmonitoring\b",
            r"\bcreate\s+alert",
            r"\btest\s+alert",
        ],
        "title": "Monitoring & alerts",
        "answer": (
            "How to set up monitoring and alerts:\n\n"
            "1. Open the **Monitoring & Alerts** section in the right sidebar.\n"
            "2. Enter Location Name, choose a condition (Vegetation Decrease, Water Area Change, "
            "Significant Overall Change), threshold %, Email, and optional Phone (SMS).\n"
            "3. Click **Create Alert** to store the rule.\n"
            "4. Click **Test Alert** to send a real test via SMTP and/or Twilio.\n\n"
            "Configure credentials in `.env` (copy from `.env.example`):\n"
            "  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD (Gmail App Password), SMTP_FROM\n"
            "  SMS_PROVIDER=twilio, SMS_API_KEY (Account SID), TWILIO_AUTH_TOKEN, SMS_FROM_NUMBER\n\n"
            "Without credentials the UI reports “not configured” or the real provider error (e.g. 535) — "
            "it never fakes a successful delivery."
        ),
        "chips": ["Create Alert", "Test Alert", "SMTP", "Twilio", ".env"],
    },
    {
        "id": "workspace",
        "triggers": [
            r"\b(how|where).*(workspace|localstorage|shared\s+(location|aoi)|persist)",
            r"\blocalstorage\b",
            r"\bsatquery_workspace",
            r"\bshared\s+(aoi|location)",
        ],
        "title": "Shared workspace (localStorage)",
        "answer": (
            "How the shared workspace works:\n\n"
            "Selecting a place on the map / search (and any drawn AOI) is stored in the browser under "
            "the key **`satquery_workspace_v1`** (localStorage).\n\n"
            "That location/AOI is reused automatically for Analysis, chat, comparison, monitoring, "
            "and reports on this device so you do not have to re-enter the place every time.\n\n"
            "Clear workspace / theme options appear under Settings when available. "
            "Clearing site data in the browser will also reset the saved AOI."
        ),
        "chips": ["satquery_workspace_v1", "localStorage", "AOI"],
    },
    {
        "id": "unavailable",
        "triggers": [
            r"\b(model_unavailable|data\s+unavailable|no\s+data|not\s+available|missing\s+data)",
            r"\bwhat\s+(to\s+do|happens)\s+when.*(unavailable|missing|fail)",
            r"\bno\s+scene\b",
            r"\bvqa\s+unavailable",
            r"\bfabricat",
        ],
        "title": "When data / MODEL is unavailable",
        "answer": (
            "What to do when data or models are unavailable:\n\n"
            "• **MODEL_UNAVAILABLE / no VLM key**: Chat and VQA fall back to evidence-only answers "
            "(NDVI/NDWI/NDBI + STAC metadata). The app **never fabricates** percentages or dates.\n"
            "• **No satellite scene**: Widen the date range or cloud-cover tolerance; check that the AOI "
            "is valid. The response states that no scene was found.\n"
            "• **Missing bands on upload**: Land-cover / index endpoints return a clear reason "
            "(e.g. “green + NIR required for NDWI”).\n"
            "• **River gauge (metres)**: India CWC live gauges are not connected — you get an explicit "
            "unavailable message. Water *extent* (km² from NDWI) is not the same as gauge level.\n"
            "• **Email/SMS**: If SMTP/Twilio are not configured, Test Alert reports “not configured” "
            "or the real provider error.\n\n"
            "Always prefer real sources + dates shown in the Answer / Sources / Execution trace panels."
        ),
        "chips": ["MODEL_UNAVAILABLE", "evidence-only", "no fabrication", "STAC"],
    },
    {
        "id": "chat_howto",
        "triggers": [
            r"\b(how|where).*(use|ask|chat|question)",
            r"\bhow\s+do\s+i\s+use\s+(this|the\s+app|satquery)",
            r"\bhelp\b",
            r"\bwhat\s+can\s+(i|you)\s+(do|ask)",
            r"\bgetting\s+started",
        ],
        "title": "Using the chat / getting started",
        "answer": (
            "How to use SatQuery AI chat and get started:\n\n"
            "1. Search a location (e.g. “Chilika Lake” or “Karur, Tamil Nadu”) or draw an AOI.\n"
            "2. Type a question in the **Ask SatQuery AI** box, or click a quick chip "
            "(Water bodies, Rainfall, Change 2024–2025, Optical + SAR, Flood risk, …).\n"
            "3. Click **Send**. Multi-turn: the same `session_id` is kept so follow-ups "
            "(“and what about vegetation?”) stay in context.\n"
            "4. Read the Answer panel, metrics, sources, confidence, and execution trace.\n"
            "5. Optional: upload a GeoTIFF, run Land Cover Analyze, Compare Images / dates, "
            "create alerts, or download a Report.\n\n"
            "Ask “how do I …” about any of these features for step-by-step help. "
            "The assistant answers from real app workflows only — it does not invent satellite data."
        ),
        "chips": ["chat", "session_id", "chips", "Send"],
    },
]


def _score(query: str, item: Dict[str, Any]) -> int:
    q = (query or "").strip().lower()
    if not q:
        return 0
    score = 0
    for pat in item["triggers"]:
        if re.search(pat, q, re.IGNORECASE):
            score += 2
    # light title keyword boost
    for token in re.findall(r"[a-z0-9_]+", item["title"].lower()):
        if len(token) > 3 and token in q:
            score += 1
    return score


def match_help(query: str) -> Optional[Dict[str, Any]]:
    """Return best FAQ match or None if not a help-style question."""
    q = (query or "").strip()
    if not q:
        return None
    # Prefer explicit help / how-to intent
    helpish = bool(
        re.search(
            r"\b(how\s+(do|to|can)|where\s+(do|to)|help|getting\s+started|what\s+can\s+i|"
            r"explain\s+how|guide\s+me|instructions?)\b",
            q,
            re.IGNORECASE,
        )
    )
    best: Optional[Tuple[int, Dict[str, Any]]] = None
    for item in FAQ:
        s = _score(q, item)
        if s <= 0:
            continue
        # Without explicit how-to/help intent, require stronger match so
        # scientific questions (e.g. NDVI values) are not treated as help.
        if not helpish and s < 4:
            continue
        if best is None or s > best[0]:
            best = (s, item)
    if best is None:
        return None
    if best[0] < 2 and not helpish:
        return None
    item = best[1]
    return {
        "success": True,
        "task": "help",
        "answer": item["answer"],
        "title": item["title"],
        "faq_id": item["id"],
        "evidence": {"faq_id": item["id"], "source": "SatQuery AI in-app help"},
        "chips": item.get("chips") or [],
        "sources": ["SatQuery AI UI / README workflow"],
        "confidence": 0.95,
        "degraded": False,
    }


def list_help_topics() -> List[str]:
    return [f["title"] for f in FAQ]
