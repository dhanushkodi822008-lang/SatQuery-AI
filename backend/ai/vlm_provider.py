"""
Pluggable Vision-Language Model provider for SatQuery AI.
Supports:
  - Hosted multimodal API (OpenAI-compatible) when VLM_API_KEY is set
  - Local HuggingFace checkpoint under models/vqa/ when available
  - Evidence-only fallback (never fabricates numbers)

Every answer is grounded with pre-computed numeric evidence injected into the prompt.
"""
from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.config import get_settings
from backend.utils.logging import logger

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore


def _encode_png(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode("ascii")


def _build_system_prompt(evidence: Dict[str, Any]) -> str:
    lines = [
        "You are SatQuery AI, a careful remote-sensing vision-language assistant.",
        "Answer ONLY using the provided image and the numeric EVIDENCE below.",
        "Never invent percentages, areas, dates, or cloud cover values.",
        "If the image or evidence is insufficient, say so clearly.",
        "Cite the evidence values you use (e.g. 'NDWI mean = 0.12, water area ≈ 3.4 km²').",
        "",
        "EVIDENCE:",
    ]
    for k, v in (evidence or {}).items():
        if v is not None:
            lines.append(f"  - {k}: {v}")
    return "\n".join(lines)


class VLMProvider:
    """Abstract interface."""

    name: str = "base"

    def available(self) -> bool:
        return False

    async def answer(
        self,
        question: str,
        image_png: Optional[bytes],
        evidence: Dict[str, Any],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError


class EvidenceOnlyProvider(VLMProvider):
    """Fallback that answers from evidence without a neural VLM."""

    name = "evidence-only"

    def available(self) -> bool:
        return True

    async def answer(
        self,
        question: str,
        image_png: Optional[bytes],
        evidence: Dict[str, Any],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        q = (question or "").lower()
        parts: List[str] = []
        loc = evidence.get("location") or evidence.get("display_name") or "the area"
        scene_date = evidence.get("scene_date") or evidence.get("acquisition_date")
        cloud = evidence.get("cloud_cover_pct")
        ndvi = evidence.get("ndvi_mean")
        ndwi = evidence.get("ndwi_mean")
        ndbi = evidence.get("ndbi_mean")
        water_km2 = evidence.get("water_area_km2")
        veg_km2 = evidence.get("vegetation_area_km2")
        built_km2 = evidence.get("builtup_area_km2")
        aoi_km2 = evidence.get("aoi_area_km2")

        parts.append(f"Analysis for {loc}.")
        if scene_date:
            parts.append(f"Latest scene date: {scene_date}.")
        if cloud is not None:
            parts.append(f"Cloud cover: {cloud}%.")
        if aoi_km2 is not None:
            parts.append(f"AOI area: {aoi_km2} km².")

        if any(w in q for w in ("water", "lake", "river", "flood", "ndwi")):
            if ndwi is not None:
                parts.append(f"NDWI mean = {ndwi}.")
            if water_km2 is not None:
                parts.append(f"Estimated water extent ≈ {water_km2} km² (spectral threshold).")
            else:
                parts.append("Water extent could not be computed from available bands.")
        elif any(w in q for w in ("vegetation", "green", "ndvi", "forest", "crop", "agri")):
            if ndvi is not None:
                parts.append(f"NDVI mean = {ndvi}.")
            if veg_km2 is not None:
                parts.append(f"Estimated vegetation/cropland-proxy ≈ {veg_km2} km².")
        elif any(w in q for w in ("built", "urban", "building", "ndbi")):
            if ndbi is not None:
                parts.append(f"NDBI mean = {ndbi}.")
            if built_km2 is not None:
                parts.append(f"Estimated built-up indication ≈ {built_km2} km².")
        else:
            # generic summary
            for label, val in (
                ("NDVI mean", ndvi),
                ("NDWI mean", ndwi),
                ("NDBI mean", ndbi),
                ("Water area km²", water_km2),
                ("Vegetation area km²", veg_km2),
            ):
                if val is not None:
                    parts.append(f"{label}: {val}.")

        if not image_png:
            parts.append("No image chip was available; answer is based on computed indices and metadata only.")

        parts.append(
            "This answer uses only computed spectral evidence and catalog metadata. "
            "No neural VLM checkpoint is loaded (set VLM_API_KEY or place models/vqa/ to enable)."
        )
        return {
            "answer": " ".join(parts),
            "confidence": 0.55 if any(v is not None for v in (ndvi, ndwi, ndbi, water_km2)) else 0.3,
            "model": self.name,
            "degraded": True,
            "sources": ["spectral_indices", "stac_metadata"],
        }


class OpenAICompatibleProvider(VLMProvider):
    """Hosted multimodal API (OpenAI / compatible endpoint)."""

    name = "openai-compatible"

    def available(self) -> bool:
        settings = get_settings()
        return bool(getattr(settings, "VLM_API_KEY", None) or os.getenv("VLM_API_KEY"))

    async def answer(
        self,
        question: str,
        image_png: Optional[bytes],
        evidence: Dict[str, Any],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        import httpx

        settings = get_settings()
        api_key = getattr(settings, "VLM_API_KEY", None) or os.getenv("VLM_API_KEY")
        base_url = getattr(settings, "VLM_BASE_URL", None) or os.getenv(
            "VLM_BASE_URL", "https://api.openai.com/v1"
        )
        model = getattr(settings, "VLM_MODEL", None) or os.getenv("VLM_MODEL", "gpt-4o-mini")

        system = _build_system_prompt(evidence)
        messages: List[Dict[str, Any]] = [{"role": "system", "content": system}]
        if history:
            for turn in history[-6:]:
                messages.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})

        content: List[Dict[str, Any]] = [{"type": "text", "text": question}]
        if image_png:
            b64 = _encode_png(image_png)
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                }
            )
        messages.append({"role": "user", "content": content})

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": model, "messages": messages, "max_tokens": 600, "temperature": 0.2}

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(f"{base_url.rstrip('/')}/chat/completions", json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
            text = data["choices"][0]["message"]["content"]
            return {
                "answer": text.strip(),
                "confidence": 0.75,
                "model": f"{self.name}:{model}",
                "degraded": False,
                "sources": ["vlm_api", "spectral_indices", "stac_metadata"],
            }
        except Exception as exc:
            logger.warning("VLM API call failed: %s", exc)
            return await EvidenceOnlyProvider().answer(question, image_png, evidence, history)


class LocalHFProvider(VLMProvider):
    """Optional local HuggingFace checkpoint under models/vqa/."""

    name = "local-hf"

    def available(self) -> bool:
        settings = get_settings()
        ckpt = settings.BASE_DIR / "models" / "vqa"
        return ckpt.exists() and any(ckpt.iterdir())

    async def answer(
        self,
        question: str,
        image_png: Optional[bytes],
        evidence: Dict[str, Any],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        # Placeholder for local inference; fall back to evidence-only with clear note.
        # Loading large VLMs is environment-specific (GPU, transformers version).
        result = await EvidenceOnlyProvider().answer(question, image_png, evidence, history)
        result["model"] = self.name
        result["answer"] = (
            "[Local HF checkpoint detected but inference not activated in this build. "
            "Using evidence-only path.] "
            + result["answer"]
        )
        result["degraded"] = True
        return result


def get_vlm_provider() -> VLMProvider:
    """Pick the best available provider."""
    for cls in (OpenAICompatibleProvider, LocalHFProvider, EvidenceOnlyProvider):
        p = cls()
        if p.available():
            return p
    return EvidenceOnlyProvider()


async def run_vlm(
    question: str,
    image_png: Optional[bytes],
    evidence: Dict[str, Any],
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    provider = get_vlm_provider()
    out = await provider.answer(question, image_png, evidence, history)
    out["provider"] = provider.name
    out["evidence"] = evidence
    return out
