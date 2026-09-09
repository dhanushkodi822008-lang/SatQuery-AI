"""
Pluggable Vision-Language Model & Groq AI provider for SatQuery AI.
Integrates Groq API with the 2,000+ question remote-sensing KnowledgeEngine (RAG),
multi-turn conversation memory, and real satellite spectral evidence.
"""
from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.config import get_settings
from backend.ai.knowledge_engine import get_knowledge_engine
from backend.utils.logging import logger

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore


def _encode_png(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode("ascii")


def _build_system_prompt(question: str, evidence: Dict[str, Any]) -> str:
    """
    Constructs the system prompt grounding the Groq model in:
    1. SatQuery AI persona and beginner-first answering guidelines.
    2. Relevant domain knowledge retrieved from the 2,000+ Q&A knowledge base.
    3. Measured numerical, temporal, and spatial satellite evidence.
    4. Strict truthfulness and zero-hallucination rules.
    """
    engine = get_knowledge_engine()
    retrieved_context = engine.format_context_for_prompt(question, top_k=4)

    lines = [
        "You are SatQuery AI, an expert AI assistant specializing in Earth observation, satellite imagery, remote sensing, GIS, agriculture, water bodies, environment, and disasters.",
        "",
        "PRIMARY ROLE & PERSONALITY:",
        "- You provide expert, trustworthy, and clear explanations of satellite data, spectral indices, maps, and remote sensing science.",
        "- You cater to BOTH beginners asking very basic questions and technical experts asking advanced questions.",
        "",
        "BEGINNER-FIRST ANSWERING RULES:",
        "1. ALWAYS START WITH A SIMPLE, ACCESSIBLE EXPLANATION: When a beginner asks a question (e.g. 'What is NDVI?', 'What is a satellite?'), provide a clear, intuitive 1-2 sentence definition first in plain language.",
        "2. PROGRESSIVE DEPTH: After the simple explanation, provide deeper details where relevant:",
        "   - How it works (physical/biological mechanism)",
        "   - Formula or technical calculation (if applicable)",
        "   - Typical interpretation / value scale (e.g. high vs low vs negative values)",
        "   - Practical real-world example or application",
        "3. STRUCTURE FOR ANALYTICAL QUESTIONS: When answering questions about specific locations, detected changes, or uploaded images, format your response with clean Markdown headers:",
        "   - **Result** (key takeaway / summary)",
        "   - **Explanation** (detailed breakdown of findings)",
        "   - **Important observations** (bullet points of measured numbers and dates)",
        "   - **Possible causes** (responsible hypotheses, noting field confirmation is needed)",
        "   - **Recommended next step** (actionable advice for user)",
        "",
        "CORE TRUTHFULNESS & ANTI-HALLUCINATION RULES:",
        "1. STRICT SATELLITE EVIDENCE: Use ONLY the provided numeric evidence and verified remote-sensing knowledge base below. NEVER invent measurements, scene IDs, acquisition dates, percentages, or satellite observations.",
        "2. NO FABRICATION ON IMAGES: If the user asks about an uploaded satellite image ('What does this image show?', 'Is there water in this image?') and NO image is provided or loaded in evidence, respond clearly: 'Please upload a satellite image so I can analyze the available visual information.' Never claim you can see an image if none is present.",
        "3. UNRELATED TOPICS: If the user asks a completely unrelated question (e.g. cooking, movies, general trivia), politely inform them that SatQuery AI specializes specifically in satellite imagery, remote sensing, GIS, agriculture, and Earth observation.",
        "4. OBSERVATIONS VS CAUSES: Satellite imagery shows spectral observations and surface changes; always note that ground verification is required to confirm specific physical causes on the ground.",
        "5. MULTI-TURN CONVERSATION MEMORY: Understand pronoun references (e.g. 'it', 'this index') referring back to earlier topics in the conversation.",
    ]

    if retrieved_context:
        lines.append("")
        lines.append(retrieved_context)

    lines.append("")
    lines.append("CURRENT SATELLITE & SENSOR EVIDENCE (from real STAC / raster analysis):")
    has_evidence = False
    for k, v in (evidence or {}).items():
        if v is not None and v != "":
            lines.append(f"  - {k}: {v}")
            has_evidence = True

    if not has_evidence:
        lines.append("  - (No specific local satellite scene loaded yet; providing scientific domain explanation)")

    return "\n".join(lines)


class VLMProvider:
    """Abstract interface for SatQuery AI models."""

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
    """Fallback provider using local knowledge base and evidence when Groq API is unavailable."""

    name = "knowledge-evidence-fallback"

    def available(self) -> bool:
        return True

    async def answer(
        self,
        question: str,
        image_png: Optional[bytes],
        evidence: Dict[str, Any],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        engine = get_knowledge_engine()
        matches = engine.search(question, top_k=2)

        parts: List[str] = []
        if matches and matches[0]["relevance_score"] >= 4.0:
            top = matches[0]
            parts.append(top["answer"])
            if len(matches) > 1 and matches[1]["relevance_score"] >= 3.0:
                parts.append(f"\n\n**Related ({matches[1]['category']}):** {matches[1]['answer']}")
        else:
            loc = evidence.get("location") or evidence.get("display_name") or "the selected area"
            scene_date = evidence.get("scene_date") or evidence.get("acquisition_date")
            cloud = evidence.get("cloud_cover_pct")
            ndvi = evidence.get("ndvi_mean")
            ndwi = evidence.get("ndwi_mean")
            ndbi = evidence.get("ndbi_mean")
            water_km2 = evidence.get("water_area_km2")
            veg_km2 = evidence.get("vegetation_area_km2")
            built_km2 = evidence.get("builtup_area_km2")
            aoi_km2 = evidence.get("aoi_area_km2")
            change_pct = evidence.get("percentage_change") or evidence.get("change_percentage")

            parts.append(f"Satellite analysis for **{loc}**.")
            if scene_date:
                parts.append(f"Observation date: {scene_date}.")
            if cloud is not None:
                parts.append(f"Cloud cover: {cloud}%.")
            if aoi_km2 is not None:
                parts.append(f"Area of Interest (AOI): {aoi_km2} km².")

            q_lower = (question or "").lower()
            if any(w in q_lower for w in ("change", "compare", "difference", "decrease", "increase")):
                if change_pct is not None:
                    parts.append(f"Detected change magnitude: approximately {change_pct}%.")
                else:
                    parts.append("Comparison indicates spectral variations between the analyzed scenes.")
            elif any(w in q_lower for w in ("water", "lake", "river", "flood", "ndwi")):
                if ndwi is not None:
                    parts.append(f"Mean NDWI: {ndwi}.")
                if water_km2 is not None:
                    parts.append(f"Detected water extent: {water_km2} km².")
            elif any(w in q_lower for w in ("vegetation", "green", "ndvi", "forest", "crop", "agri")):
                if ndvi is not None:
                    parts.append(f"Mean NDVI: {ndvi}.")
                if veg_km2 is not None:
                    parts.append(f"Vegetated surface extent: {veg_km2} km².")
            elif any(w in q_lower for w in ("built", "urban", "building", "ndbi")):
                if ndbi is not None:
                    parts.append(f"Mean NDBI: {ndbi}.")
                if built_km2 is not None:
                    parts.append(f"Built-up surface extent: {built_km2} km².")

        return {
            "answer": "\n".join(parts) if parts else "SatQuery AI analyzed the available satellite parameters for your query.",
            "confidence": 0.85 if matches else 0.6,
            "model": self.name,
            "degraded": True,
            "sources": ["satquery_knowledge_base", "spectral_indices"],
        }


class GroqAIProvider(VLMProvider):
    """
    Hosted Groq AI Provider.
    Communicates securely with Groq API endpoints using the server-side GROQ_API_KEY.
    """

    name = "groq-ai"

    def available(self) -> bool:
        settings = get_settings()
        key = (
            getattr(settings, "GROQ_API_KEY", None)
            or getattr(settings, "VLM_API_KEY", None)
            or os.getenv("GROQ_API_KEY")
            or os.getenv("VLM_API_KEY")
        )
        return bool(key and str(key).strip())

    async def answer(
        self,
        question: str,
        image_png: Optional[bytes],
        evidence: Dict[str, Any],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        import httpx

        settings = get_settings()
        api_key = (
            getattr(settings, "GROQ_API_KEY", None)
            or getattr(settings, "VLM_API_KEY", None)
            or os.getenv("GROQ_API_KEY")
            or os.getenv("VLM_API_KEY")
            or ""
        ).strip()

        base_url = (
            getattr(settings, "VLM_BASE_URL", None)
            or os.getenv("VLM_BASE_URL", "https://api.groq.com/openai/v1")
        ).rstrip("/")

        model = (
            getattr(settings, "GROQ_MODEL", None)
            or getattr(settings, "VLM_MODEL", None)
            or os.getenv("GROQ_MODEL")
            or os.getenv("VLM_MODEL", "openai/gpt-oss-120b")
        )

        # Ensure correct base URL for Groq keys
        if api_key.startswith("gsk_") and "groq.com" not in base_url:
            base_url = "https://api.groq.com/openai/v1"

        system_prompt = _build_system_prompt(question, evidence)
        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]

        # Inject up to last 8 turns of conversation history for multi-turn context
        if history:
            for turn in history[-8:]:
                role = turn.get("role", "user")
                if role in ("user", "assistant"):
                    content = str(turn.get("content", ""))
                    if content:
                        messages.append({"role": role, "content": content})

        # Append current user question
        messages.append({"role": "user", "content": question})

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # Try primary model, with automatic fallback to secondary models if model not found
        candidate_models = [model, "openai/gpt-oss-120b", "llama-3.3-70b-versatile", "qwen/qwen3.8-27b"]
        last_exception = None

        for cand_model in candidate_models:
            payload = {
                "model": cand_model,
                "messages": messages,
                "max_tokens": 1024,
                "temperature": 0.2,
            }

            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    r = await client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
                    if r.status_code == 404:
                        # Model not found on Groq, try next candidate
                        continue
                    r.raise_for_status()
                    data = r.json()

                response_text = data["choices"][0]["message"]["content"].strip()
                return {
                    "answer": response_text,
                    "confidence": 0.95,
                    "model": f"{self.name}:{cand_model}",
                    "degraded": False,
                    "sources": ["groq_api", "satquery_knowledge_base", "spectral_indices", "stac_metadata"],
                }
            except Exception as exc:
                last_exception = exc
                logger.warning("Groq API call attempt with model %s failed: %s", cand_model, exc)

        logger.error("All Groq API attempts failed (%s). Falling back to KnowledgeEngine evidence.", last_exception)
        fallback = await EvidenceOnlyProvider().answer(question, image_png, evidence, history)
        fallback["error_message"] = "SatQuery AI used local knowledge base retrieval because the Groq API was temporarily unreachable."
        return fallback


def get_vlm_provider() -> VLMProvider:
    """Pick the best available provider (Groq AI preferred)."""
    groq = GroqAIProvider()
    if groq.available():
        return groq
    return EvidenceOnlyProvider()


async def run_vlm(
    question: str,
    image_png: Optional[bytes],
    evidence: Dict[str, Any],
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Execute AI response generation using Groq and the KnowledgeEngine."""
    provider = get_vlm_provider()
    out = await provider.answer(question, image_png, evidence, history)
    out["provider"] = provider.name
    out["evidence"] = evidence
    return out
