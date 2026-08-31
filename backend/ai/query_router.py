"""
Agentic Query Router.
Classifies natural language queries into specialist tasks.
Shows full execution trace.
"""
from typing import Any, Dict, List, Tuple
import re
from backend.ai.model_registry import get_registry


TASK_PATTERNS: List[Tuple[str, List[str]]] = [
    ("water_level", [r"water\s*level", r"gauge", r"river\s*level", r"how\s+high\s+is\s+the\s+(river|water)", r"metres?\s+(level|depth)"]),
    ("flood_risk", [r"flood\s*risk", r"flooding", r"will\s+it\s+flood", r"flood\s+danger", r"inundation\s+risk"]),
    ("weather", [r"rainfall", r"temperature", r"weather", r"rain\b", r"humidity", r"wind\b", r"forecast", r"precipitation"]),
    ("change_detection", [r"what\s+changed", r"change\s+between", r"compare.*year", r"multitemporal", r"from\s+20\d{2}\s+to\s+20\d{2}", r"increased", r"decreased", r"has\s+the\s+water\s+extent"]),
    ("optical_sar", [r"optical\s+and\s+sar", r"optical\s*\+\s*sar", r"sentinel-?1\s+and\s+sentinel-?2", r"sar\s+and\s+optical", r"fuse.*sar"]),
    ("water_analysis", [r"water\s*bod", r"how\s+much\s+water", r"show\s+(the\s+)?(river|lake|water)", r"is\s+there\s+water", r"water\s+in\s+(this|the)\s+area", r"water\s+extent", r"water\s+coverage", r"rivers?\s+and\s+lakes"]),
    ("agriculture", [r"agricultur", r"cropland", r"farmland", r"how\s+much\s+(farm|crop|agri)", r"cultivated"]),
    ("builtup", [r"built-?up", r"urban", r"buildings?", r"settlement", r"how\s+much\s+(built|urban)"]),
    ("vegetation", [r"vegetation", r"ndvi", r"green\s+cover", r"forest", r"land\s*cover"]),
    ("captioning", [r"describe\s+(this|the)\s+(image|scene|satellite)", r"caption"]),
    ("grounding", [r"show\s+me\s+where", r"locate\s+", r"point\s+to", r"grounding"]),
    ("vqa", [r"what\s+is\s+in\s+(this|the)\s+image", r"vqa"]),
    ("report", [r"generate\s+(a\s+)?report", r"download\s+report", r"export\s+analysis"]),
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
        "agriculture": "landcover",
        "builtup": "ndbi_builtup",
        "vegetation": "ndvi_veg",
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
