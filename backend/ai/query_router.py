"""
Agentic Query Router.
Classifies natural language queries into specialist tasks and action intents.
Provides full execution tracing and structured action payloads.
"""
from typing import Any, Dict, List, Tuple
import re
from backend.ai.model_registry import get_registry


TASK_PATTERNS: List[Tuple[str, List[str]]] = [
    ("basemap_switch", [
        r"switch\s+to\s+(satellite|street|default)\s+(map|view|layer)?",
        r"show\s+(satellite|street|osm)\s+(imagery|layer|map|view)",
        r"(satellite|street|default)\s+view",
    ]),
    ("coordinate_search", [
        r"(?:find|go\s+to|locate|show|center\s+on)\s+(?:latitude\s+)?([+-]?\d+\.?\d*)\s*[, ]\s*(?:longitude\s+)?([+-]?\d+\.?\d*)",
        r"which\s+(district|state|country|place|city)\s+is\s+at\s+([+-]?\d+\.?\d*)",
        r"use\s+these\s+coordinates",
        r"set\s+this\s+location\s+as\s+(my\s+)?aoi",
    ]),
    ("boundary_selection", [
        r"(select|show|use|get)\s+(the\s+)?(actual|real|complete|entire|official)?\s*(administrative\s+)?boundary",
        r"(select|show|use)\s+(the\s+)?(complete|entire|whole)\s+(district|state|city|town|village)",
        r"(select|show|use)\s+.+\s+(district|state|city|town|village)\s+boundary",
        r"use\s+this\s+boundary\s+as\s+(my\s+)?(aoi|study\s+area)",
        r"make\s+this\s+boundary\s+my\s+(study\s+area|aoi)",
    ]),
    ("ndvi_analysis", [
        r"(calculate|compute|show|get)\s+ndvi",
        r"(show|analyze|where\s+is)\s+(vegetation|agriculture|crops|farmland|canopy|forest)(\s+health|\s+stress)?",
        r"calculate\s+vegetation\s+index",
        r"has\s+vegetation\s+(decreased|increased|changed)",
        r"show\s+vegetation\s+change",
        r"compare\s+vegetation",
    ]),
    ("ndwi_analysis", [
        r"(calculate|compute|show|get)\s+ndwi",
        r"(show|find|detect|where\s+is|analyze)\s+water(\s+bodies|\s+extent)?",
        r"has\s+water\s+(increased|decreased|changed)",
        r"show\s+water\s+change",
    ]),
    ("ndbi_analysis", [
        r"(calculate|compute|show|get)\s+ndbi",
        r"(show|find|analyze)\s+(built-?up|urban)\s*(areas|growth)?",
        r"has\s+(urbanization|built-?up\s+area)\s+increased",
        r"show\s+urban\s+growth",
    ]),
    ("location_search", [
        r"^(find|show|locate|go\s+to|zoom\s+to|where\s+is|select)\s+(?!(?:water|vegetation|agriculture|forest|built-?up|ndvi|ndwi|ndbi)\b)([a-zA-Z\s]+(?:\s+district|\s+state|\s+city|\s+town|\s+village)?)$",
        r"(use|set|make)\s+([a-zA-Z\s]+)\s+as\s+(my\s+)?(study\s+area|aoi|active\s+area)",
        r"find\s+(this\s+)?(village|town|city|district|state)",
        r"select\s+(namakkal|karur|salem|chennai|tamil\s+nadu|india|[a-zA-Z\s]+(?:\s+district)?)",
    ]),
    ("aoi_control", [
        r"clear\s+(my\s+)?(aoi|area|selection|polygon)",
        r"show\s+(my\s+)?aoi",
        r"change\s+(my\s+)?aoi",
        r"use\s+my\s+current\s+aoi",
        r"analyze\s+my\s+current\s+area",
        r"(draw|create)\s+(an\s+)?(aoi|polygon|rectangle|circle)",
    ]),
    ("help", [
        r"how\s+(do|to|can)\s+i",
        r"how\s+to\s+(select|draw|upload|calculate|search|compare|set\s+up|use)",
        r"getting\s+started",
        r"\bhelp\b",
        r"what\s+can\s+(i|you)\s+(do|ask)",
        r"instructions?",
        r"where\s+(do|can)\s+i\s+(draw|select|upload|define)",
    ]),
    ("image_analysis", [
        r"analyze\s+(this|the)\s+(uploaded\s+)?(image|satellite\s+image|aerial\s+image)",
        r"what\s+does\s+this\s+(satellite\s+)?image\s+show",
        r"describe\s+(this|the)\s+(image|satellite\s+image|scene)",
        r"find\s+(vegetation|water|built-?up|roads|features)\s+in\s+this\s+image",
        r"identify\s+land\s+features",
    ]),
    ("chart", [
        r"\b(show|plot|graph|chart)\b.*\b(ndvi|ndwi|ndbi|evi|vegetation|water|cloud)",
        r"\b(ndvi|ndwi|ndbi)\b.*\b(chart|plot|graph|by\s+year|over\s+time)",
        r"line\s+chart",
        r"bar\s+chart",
        r"pie\s+chart",
        r"time[- ]series",
        r"land-?cover\s+percent",
        r"\b(show|plot|graph)\b.*\b(from|between)\s+(19|20)\d{2}",
    ]),
    ("year_compare", [
        r"compare\s+.+\s+(19|20)\d{2}\s+(and|to|with|vs\.?)\s+(19|20)\d{2}",
        r"(19|20)\d{2}\s+(and|to|vs\.?|versus)\s+(19|20)\d{2}",
        r"year[- ]to[- ]year",
        r"between\s+(19|20)\d{2}\s+and\s+(19|20)\d{2}",
        r"from\s+(19|20)\d{2}\s+to\s+(19|20)\d{2}",
        r"vegetation\s+change\s+from\s+(19|20)\d{2}",
        r"water\s+changed?\s+between\s+(19|20)\d{2}",
    ]),
    ("date_compare", [
        r"compare\s+.+\d{4}-\d{2}-\d{2}",
        r"\d{4}-\d{2}-\d{2}\s+(and|to|vs)",
        r"specific\s+dates?",
        r"date\s*[ab]\b",
    ]),
    ("change_detection", [
        r"what\s+changed",
        r"show\s+changes?",
        r"detect\s+change",
        r"compare\s+these\s+two\s+dates",
        r"compare\s+2024\s+and\s+2025",
        r"what\s+changed\s+between\s+2024\s+and\s+2025",
        r"where\s+are\s+the\s+major\s+changes",
        r"show\s+changed\s+areas",
        r"analyze\s+change\s+over\s+time",
        r"multitemporal",
    ]),
    ("remote_sensing_question", [
        r"what\s+is\s+(ndvi|ndwi|ndbi|evi|savi|sentinel|landsat|sar|spatial\s+resolution|temporal|remote\s+sensing|gis)",
        r"difference\s+between\s+(ndvi|ndwi|sentinel|landsat|optical|sar)",
        r"which\s+(index|satellite|bands?)\s+(is|are|should|for)",
        r"why\s+(is|does)\s+(ndvi|cloud|sar)",
        r"what\s+does\s+(ndvi|ndwi|cloud\s+cover)\s+(mean|measure)",
        r"bands?\s+used\s+for",
    ]),
    ("water_level", [r"water\s*level", r"gauge", r"river\s*level", r"how\s+high\s+is\s+the\s+(river|water)", r"metres?\s+(level|depth)"]),
    ("flood_risk", [r"flood\s*risk", r"flooding", r"will\s+it\s+flood", r"flood\s+danger", r"inundation\s+risk", r"flood-?affected"]),
    ("weather", [r"rainfall", r"temperature", r"weather", r"rain\b", r"humidity", r"wind\b", r"forecast", r"precipitation"]),
    ("optical_sar", [r"optical\s+and\s+sar", r"optical\s*\+\s*sar", r"sentinel-?1\s+and\s+sentinel-?2", r"sar\s+and\s+optical", r"fuse.*sar"]),
    ("water_analysis", [r"water\s*bod", r"how\s+much\s+water", r"show\s+(the\s+)?(river|lake|water)", r"is\s+there\s+water", r"water\s+in\s+(this|the)\s+area", r"water\s+extent", r"water\s+coverage", r"rivers?\s+and\s+lakes"]),
    ("agriculture", [r"agricultur", r"cropland", r"farmland", r"how\s+much\s+(farm|crop|agri)", r"cultivated"]),
    ("builtup", [r"built-?up", r"urban", r"buildings?", r"settlement", r"how\s+much\s+(built|urban)"]),
    ("vegetation", [r"vegetation", r"\bndvi\b", r"green\s+cover", r"forest", r"land\s*cover"]),
    ("captioning", [r"describe\s+(this|the)\s+(image|scene|satellite)", r"caption"]),
    ("grounding", [r"show\s+me\s+where", r"locate\s+", r"point\s+to", r"grounding"]),
    ("vqa", [r"what\s+is\s+in\s+(this|the)\s+image", r"vqa"]),
    ("report", [r"generate\s+(a\s+)?report", r"download\s+report", r"export\s+analysis"]),
    ("satellite_search", [r"find\s+satellite", r"search\s+(for\s+)?(imagery|scenes?)", r"available\s+(imagery|data|scenes?)", r"do\s+we\s+have\s+(sentinel|landsat)"]),
]


def route_query(query: str) -> Dict[str, Any]:
    q = (query or "").strip().lower()
    registry = get_registry()
    matched_task = "vqa"  # default fallback
    matched_patterns = []

    for task, patterns in TASK_PATTERNS:
        for p in patterns:
            if re.search(p, q, re.IGNORECASE):
                matched_task = task
                matched_patterns.append(p)
                break
        if matched_patterns:
            break

    model_key_map = {
        "water_analysis": "ndwi_water",
        "ndwi_analysis": "ndwi_water",
        "agriculture": "landcover",
        "builtup": "ndbi_builtup",
        "ndbi_analysis": "ndbi_builtup",
        "vegetation": "ndvi_veg",
        "ndvi_analysis": "ndvi_veg",
        "change_detection": "change_detection",
        "optical_sar": "optical_sar_fusion",
        "flood_risk": "flood_risk",
        "vqa": "vqa",
        "captioning": "captioning",
        "grounding": "grounding",
        "weather": "query_router",
        "water_level": "query_router",
        "report": "query_router",
    }
    model_key = model_key_map.get(matched_task, "vqa")
    model = registry.get(model_key)

    return {
        "query": query,
        "detected_task": matched_task,
        "matched_patterns": matched_patterns,
        "selected_model": model.to_dict() if model else None,
        "model_status": model.status if model else "UNKNOWN",
        "router": "QueryRouter (rule-based agentic)",
    }
