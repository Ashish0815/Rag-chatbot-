"""Phase 4 — Embedder.

Embeds text with all-MiniLM-L6-v2 and exposes embed() for both corpus chunks
(ingestion) and live user queries (retrieval), so both sides of the RAG
pipeline share the same embedding space.

Uses Chroma's ONNX build of the same model (identical vectors to
sentence-transformers/all-MiniLM-L6-v2, cosine similarity 1.0) so the app
doesn't need torch, which is too large for a 512 MB deployment.
"""
from __future__ import annotations

from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

MODEL_NAME = "all-MiniLM-L6-v2"

_model: ONNXMiniLM_L6_V2 | None = None


def get_model() -> ONNXMiniLM_L6_V2:
    global _model
    if _model is None:
        _model = ONNXMiniLM_L6_V2()
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    return [vector.tolist() for vector in get_model()(texts)]
