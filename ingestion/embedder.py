"""Phase 4 — Embedder.

Loads sentence-transformers/all-MiniLM-L6-v2 once and exposes embed() for
both corpus chunks (ingestion) and live user queries (retrieval), so both
sides of the RAG pipeline share the same embedding space.
"""
from __future__ import annotations

from sentence_transformers import SentenceTransformer

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    return get_model().encode(texts, convert_to_numpy=True).tolist()
