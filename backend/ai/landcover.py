from typing import Any, Dict
from backend.ai.model_registry import get_registry


def estimate_agriculture(context: Dict[str, Any]) -> Dict[str, Any]:
    model = get_registry()["landcover"]
    return {
        "success": True,
        "task": "agriculture",
        "model": model.to_dict(),
        "quantitative_result": None,
        "message": (
            "Agriculture / land-cover classification requires a trained model (e.g. BigEarthNet) "
            "or an authoritative land-use dataset. "
            "NDVI can indicate vegetation but is not a direct agricultural land classifier. "
            f"Model status: {model.status}."
        ),
        "status": model.status,
        "note": "No agricultural area percentage is fabricated.",
    }
