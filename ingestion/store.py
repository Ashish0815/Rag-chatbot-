"""Phase 4 — Vector Store.

Persists chunks + embeddings + metadata into a local ChromaDB collection.
"""
from __future__ import annotations

from pathlib import Path

import chromadb

from ingestion.chunker import Chunk

PERSIST_DIR = Path("data/chroma")
COLLECTION_NAME = "hdfc_mf_faq"


def get_client() -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=str(PERSIST_DIR))


def reset_collection(client: chromadb.ClientAPI) -> chromadb.Collection:
    """Delete-then-recreate so re-running ingestion rebuilds the collection cleanly."""
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    return client.create_collection(COLLECTION_NAME)


def upsert(collection: chromadb.Collection, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
    collection.upsert(
        ids=[c.chunk_id for c in chunks],
        embeddings=embeddings,
        documents=[c.text for c in chunks],
        metadatas=[
            {
                "scheme_name": c.scheme_name,
                "category": c.category,
                "source_url": c.source_url,
                "fetched_at": c.fetched_at,
            }
            for c in chunks
        ],
    )
