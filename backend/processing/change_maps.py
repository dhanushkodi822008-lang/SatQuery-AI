"""Change detection statistics between two dated observations."""
from typing import Any, Dict, Optional


def compute_change_stats(
    before: Dict[str, Any],
    after: Dict[str, Any],
    metric_key: str = "value",
) -> Dict[str, Any]:
    """
    Compare two real observations. If either quantitative value is missing,
    report unavailable rather than inventing change %.
    """
    b = before.get(metric_key)
    a = after.get(metric_key)
    if b is None or a is None:
        return {
            "success": False,
            "error": "Cannot compute change: one or both quantitative values unavailable",
            "before": before,
            "after": after,
        }
    try:
        b_f, a_f = float(b), float(a)
    except (TypeError, ValueError):
        return {"success": False, "error": "Non-numeric values"}

    abs_change = a_f - b_f
    pct = ((a_f - b_f) / b_f * 100.0) if b_f != 0 else None
    return {
        "success": True,
        "before_value": b_f,
        "after_value": a_f,
        "absolute_change": round(abs_change, 4),
        "percent_change": round(pct, 2) if pct is not None else None,
        "before_date": before.get("acquisition_date"),
        "after_date": after.get("acquisition_date"),
        "unit": before.get("unit") or after.get("unit"),
    }
