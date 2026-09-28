"""Phase 4 — Ingestion CLI entrypoint.

Loading -> Chunking -> Embedding -> Store Vector Data.
Re-running rebuilds the ChromaDB collection from scratch (idempotent).
"""
from __future__ import annotations

from ingestion.chunker import get_chunks
from ingestion.embedder import embed
from ingestion.loader import load_sources, save_raw_documents
from ingestion.store import COLLECTION_NAME, get_client, reset_collection, upsert


def run() -> None:
    print("Loading source pages...")
    docs = load_sources()
    save_raw_documents(docs)
    print(f"  loaded {len(docs)} document(s), raw text saved to data/raw/")

    print("Chunking...")
    all_chunks = [chunk for doc in docs for chunk in get_chunks(doc)]
    print(f"  produced {len(all_chunks)} chunk(s)")

    print("Embedding...")
    embeddings = embed([c.text for c in all_chunks])
    print(f"  embedded {len(embeddings)} chunk(s)")

    print(f"Writing to ChromaDB collection '{COLLECTION_NAME}'...")
    client = get_client()
    collection = reset_collection(client)
    upsert(collection, all_chunks, embeddings)

    print("\nIngestion summary")
    print(f"  schemes processed: {len(docs)}")
    print(f"  total chunks:      {len(all_chunks)}")
    print(f"  collection size:   {collection.count()}")


if __name__ == "__main__":
    run()
