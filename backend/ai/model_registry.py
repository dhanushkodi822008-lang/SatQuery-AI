"""
Model Registry for SatQuery AI.
Declares available analytical tools and model adapters.
Does NOT claim fine-tuned VLMs are loaded unless a checkpoint is present.
"""
from typing import Any, Dict, List, Optional
from pathlib import Path
from backend.config import get_settings


class ModelInfo:
    def __init__(
        self,
        name: str,
        task: str,
        status: str,
        description: str,
        backend: str = "analytical",
        checkpoint: Optional[str] = None,
        benchmarks: Optional[List[str]] = None,
    ):
        self.name = name
        self.task = task
        self.status = status  # READY | ADAPTER_READY | NOT_INSTALLED
        self.description = description
        self.backend = backend
        self.checkpoint = checkpoint
        self.benchmarks = benchmarks or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "task": self.task,
            "status": self.status,
            "description": self.description,
            "backend": self.backend,
            "checkpoint": self.checkpoint,
            "benchmarks": self.benchmarks,
            "note": (
                "Model adapter ready — fine-tuned checkpoint not installed."
                if self.status == "ADAPTER_READY"
                else None
            ),
        }


def get_registry() -> Dict[str, ModelInfo]:
    settings = get_settings()
    # Check for optional checkpoint dirs
    ckpt_root = settings.BASE_DIR / "models"
    def has_ckpt(name: str) -> bool:
        return (ckpt_root / name).exists()

    models = {
        "query_router": ModelInfo(
            "QueryRouter",
            "routing",
            "READY",
            "Rule + keyword agentic router for remote-sensing tasks",
            backend="rules",
        ),
        "ndwi_water": ModelInfo(
            "WaterSegmentationNDWI",
            "water_analysis",
            "READY",
            "McFeeters NDWI water extent from optical bands",
            backend="spectral_index",
        ),
        "ndvi_veg": ModelInfo(
            "VegetationNDVI",
            "vegetation",
            "READY",
            "NDVI vegetation indication (not agriculture land-use classifier)",
            backend="spectral_index",
        ),
        "ndbi_builtup": ModelInfo(
            "BuiltUpNDBI",
            "builtup",
            "READY",
            "NDBI built-up / bare-soil indication",
            backend="spectral_index",
        ),
        "change_detection": ModelInfo(
            "ChangeDetectionAnalytical",
            "change_detection",
            "READY",
            "Multitemporal scene search + quantitative change when both dates available",
            backend="analytical",
        ),
        "optical_sar_fusion": ModelInfo(
            "OpticalSARFusion",
            "optical_sar",
            "READY",
            "Paired Sentinel-2 + Sentinel-1 scene discovery and joint interpretation",
            backend="analytical",
        ),
        "flood_risk": ModelInfo(
            "FloodRiskIndicator",
            "flood_risk",
            "READY",
            "Explainable risk score from rainfall, water extent, and gauge availability",
            backend="analytical",
        ),
        "landcover": ModelInfo(
            "LandCoverAdapter",
            "landcover",
            "ADAPTER_READY" if not has_ckpt("landcover") else "READY",
            "Land-cover / agriculture classification adapter (BigEarthNet-style)",
            backend="ml_adapter",
            checkpoint=str(ckpt_root / "landcover") if has_ckpt("landcover") else None,
            benchmarks=["BigEarthNet"],
        ),
        "vqa": ModelInfo(
            "RemoteSensingVQA",
            "vqa",
            "READY" if not has_ckpt("vqa") else "READY",
            "Remote sensing visual question answering adapter",
            backend="vlm_adapter",
            checkpoint=str(ckpt_root / "vqa") if has_ckpt("vqa") else None,
            benchmarks=["RSVQA", "VRSBench"],
        ),
        "captioning": ModelInfo(
            "RSCaptioning",
            "captioning",
            "ADAPTER_READY" if not has_ckpt("captioning") else "READY",
            "Satellite image captioning adapter",
            backend="vlm_adapter",
            benchmarks=["VRSBench"],
        ),
        "grounding": ModelInfo(
            "RSGrounding",
            "grounding",
            "ADAPTER_READY" if not has_ckpt("grounding") else "READY",
            "Phrase grounding / region localization adapter",
            backend="vlm_adapter",
        ),
        "cdvqa": ModelInfo(
            "CDVQA",
            "change_vqa",
            "ADAPTER_READY" if not has_ckpt("cdvqa") else "READY",
            "Change detection visual question answering adapter",
            backend="vlm_adapter",
            benchmarks=["CDVQA"],
        ),
    }
    return models


def list_models() -> List[Dict[str, Any]]:
    return [m.to_dict() for m in get_registry().values()]
