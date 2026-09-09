"""
SatQuery AI — Sub-millisecond Knowledge Retrieval Engine (RAG).
Indexes and searches the 2,000+ remote sensing Q&A dataset to ground
Groq AI responses with domain accuracy and beginner-first explanations.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.config import get_settings
from backend.utils.logging import logger

STOPWORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's",
    "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other",
    "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "shan't",
    "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves", "tell", "explain", "give", "show", "please", "me"
}

# Domain acronyms and keywords to preserve and boost
DOMAIN_KEYWORDS: Set[str] = {
    "ndvi", "ndwi", "ndbi", "evi", "savi", "ndre", "msavi", "ndmi", "nbr",
    "sentinel", "sentinel-1", "sentinel-2", "landsat", "modis", "isro", "nasa", "esa",
    "copernicus", "sar", "radar", "optical", "stac", "geotiff", "cog", "wgs84", "utm",
    "gis", "gps", "aoi", "dem", "pixel", "resolution", "spatial", "temporal",
    "spectral", "radiometric", "reflectance", "chlorophyll", "biomass", "canopy",
    "crop", "agriculture", "flood", "disaster", "water", "forest", "deforestation",
    "urban", "builtup", "built-up", "classification", "segmentation", "vlm", "cnn"
}


def tokenize(text: str) -> List[str]:
    """Tokenize and normalize text into meaningful keywords."""
    if not text:
        return []
    # Replace punctuation with space, preserving hyphens in compound words
    cleaned = re.sub(r"[^\w\s\-]", " ", text.lower())
    tokens = []
    for raw in cleaned.split():
        token = raw.strip("-")
        if not token or len(token) < 2:
            continue
        tokens.append(token)
    return tokens


class KnowledgeEngine:
    """
    In-memory BM25 + Keyword-boosted retrieval engine for SatQuery AI.
    Loads and indexes ~2,000+ Q&A entries in < 20ms.
    """

    def __init__(self, dataset_path: Optional[Path] = None):
        if dataset_path is None:
            settings = get_settings()
            dataset_path = settings.DATA_DIR / "knowledge_base.json"
            if not dataset_path.exists():
                dataset_path = settings.BASE_DIR / "data" / "knowledge_base.json"

        self.dataset_path = Path(dataset_path)
        self.documents: List[Dict[str, Any]] = []
        self.doc_tokens: List[List[str]] = []
        self.inverted_index: Dict[str, List[int]] = defaultdict(list)
        self.doc_lengths: List[int] = []
        self.avg_doc_len: float = 0.0
        self.idf: Dict[str, float] = {}
        self.k1: float = 1.5
        self.b: float = 0.75
        self._loaded: bool = False
        self.load()

    def load(self) -> None:
        """Load knowledge base JSON and build the inverted index."""
        if not self.dataset_path.exists():
            logger.warning("Knowledge base file not found at %s", self.dataset_path)
            return

        try:
            with open(self.dataset_path, "r", encoding="utf-8") as f:
                self.documents = json.load(f)

            num_docs = len(self.documents)
            if num_docs == 0:
                logger.warning("Knowledge base is empty")
                return

            self.doc_tokens = []
            self.inverted_index = defaultdict(list)
            self.doc_lengths = []
            df: Dict[str, int] = defaultdict(int)

            for doc_id, doc in enumerate(self.documents):
                # Form searchable text from question, answer, category, keywords, and intent
                q_text = doc.get("question", "")
                a_text = doc.get("answer", "")
                cat_text = doc.get("category", "")
                kw_text = " ".join(doc.get("keywords", []))
                intent_text = doc.get("intent", "").replace("_", " ")

                # Combine with question weighting (repeat question tokens to give higher relevance)
                combined = f"{q_text} {q_text} {a_text} {cat_text} {kw_text} {kw_text} {intent_text}"
                tokens = tokenize(combined)
                self.doc_tokens.append(tokens)
                self.doc_lengths.append(len(tokens))

                unique_terms = set(tokens)
                for term in unique_terms:
                    self.inverted_index[term].append(doc_id)
                    df[term] += 1

            self.avg_doc_len = sum(self.doc_lengths) / max(num_docs, 1)

            # Compute BM25 IDF for all terms
            self.idf = {}
            for term, count in df.items():
                # Standard BM25 IDF formula with +1 smoothing
                self.idf[term] = math.log((num_docs - count + 0.5) / (count + 0.5) + 1.0)

            self._loaded = True
            logger.info("KnowledgeEngine loaded %d items from %s (avg len=%.1f)", num_docs, self.dataset_path.name, self.avg_doc_len)
        except Exception as exc:
            logger.exception("Failed to load knowledge base: %s", exc)

    def search(
        self,
        query: str,
        top_k: int = 4,
        min_score: float = 1.0,
        filter_category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search knowledge base for top matching questions and answers.
        Returns scored results in ranked order.
        """
        if not self._loaded or not self.documents:
            return []

        q_clean = (query or "").strip().lower()
        if not q_clean:
            return []

        q_tokens = tokenize(q_clean)
        if not q_tokens:
            return []

        scores: Dict[int, float] = defaultdict(float)
        matched_terms: Dict[int, Set[str]] = defaultdict(set)

        # Check for exact string match on question first
        for doc_id, doc in enumerate(self.documents):
            doc_q = doc.get("question", "").lower().strip()
            if q_clean == doc_q or q_clean.rstrip("?") == doc_q.rstrip("?"):
                scores[doc_id] += 50.0
                matched_terms[doc_id].add("exact_question_match")

        # Evaluate BM25 scoring across matching query tokens
        for token in q_tokens:
            posting = self.inverted_index.get(token)
            if not posting:
                # Check for substring match on key acronyms
                for key_term, doc_ids in self.inverted_index.items():
                    if len(token) >= 3 and (token in key_term or key_term in token):
                        posting = doc_ids
                        break
            if not posting:
                continue

            term_idf = self.idf.get(token, 1.0)
            # Boost domain keywords (e.g. ndvi, sar, sentinel, crop)
            if token in DOMAIN_KEYWORDS:
                term_idf *= 2.5

            for doc_id in posting:
                if filter_category and self.documents[doc_id].get("category") != filter_category:
                    continue

                doc_len = self.doc_lengths[doc_id]
                tokens_list = self.doc_tokens[doc_id]
                tf = tokens_list.count(token)
                matched_terms[doc_id].add(token)

                # BM25 term frequency saturation
                num = tf * (self.k1 + 1.0)
                denom = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avg_doc_len))
                term_score = term_idf * (num / denom)
                scores[doc_id] += term_score

        # Boost for matching keywords in doc keywords list
        for doc_id, score in list(scores.items()):
            doc = self.documents[doc_id]
            kw_list = [k.lower() for k in doc.get("keywords", [])]
            for kw in kw_list:
                if kw in q_clean:
                    scores[doc_id] += 4.0
            # Extra boost if intent words overlap
            doc_intent = doc.get("intent", "").lower()
            for token in q_tokens:
                if token in doc_intent and token not in STOPWORDS:
                    scores[doc_id] += 2.0

        if not scores:
            return []

        # Sort candidate documents by score
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)

        results: List[Dict[str, Any]] = []
        for doc_id, score in ranked[:top_k]:
            if score < min_score and len(results) > 0:
                continue
            doc = self.documents[doc_id]
            results.append({
                "question": doc.get("question"),
                "answer": doc.get("answer"),
                "category": doc.get("category"),
                "intent": doc.get("intent"),
                "keywords": doc.get("keywords", []),
                "difficulty": doc.get("difficulty", "beginner"),
                "relevance_score": round(score, 3),
                "matched_terms": list(matched_terms[doc_id]),
            })

        return results

    def format_context_for_prompt(self, query: str, top_k: int = 3) -> str:
        """
        Builds a clean, structured context string for injection into the Groq prompt.
        """
        matches = self.search(query, top_k=top_k)
        if not matches:
            return ""

        lines = [
            "DOMAIN KNOWLEDGE BASE (Verified Satellite & Remote Sensing Ground Truth):",
            "Use the following domain definitions to formulate your answer with beginner-friendly clarity:",
        ]
        for idx, m in enumerate(matches, 1):
            lines.append(f"\n[Reference #{idx} - Category: {m['category']}]")
            lines.append(f"Q: {m['question']}")
            lines.append(f"A: {m['answer']}")

        return "\n".join(lines)


# Global singleton instance
_engine_instance: Optional[KnowledgeEngine] = None


def get_knowledge_engine() -> KnowledgeEngine:
    """Get or initialize the singleton KnowledgeEngine instance."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = KnowledgeEngine()
    return _engine_instance


def search_knowledge(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """Helper function to search the knowledge base."""
    engine = get_knowledge_engine()
    return engine.search(query, top_k=top_k)
