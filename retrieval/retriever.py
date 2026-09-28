"""Phase 6 — Retriever.

Embeds the user query with the same model used at ingestion time and runs
a top-k similarity search against the ChromaDB collection, optionally
filtered to a single scheme when the query names one.
"""
from __future__ import annotations

from dataclasses import dataclass

from ingestion.embedder import embed
from ingestion.store import COLLECTION_NAME, get_client
from retrieval.scheme_lookup import find_scheme


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    scheme_name: str
    category: str
    source_url: str
    fetched_at: str
    score: float  # Chroma L2 distance; lower means more similar


def _run_query(query: str, k: int, where: dict | None) -> list[RetrievedChunk]:
    client = get_client()
    collection = client.get_collection(COLLECTION_NAME)

    query_embedding = embed([query])[0]
    result = collection.query(query_embeddings=[query_embedding], n_results=k, where=where)

    if not result["ids"][0]:
        return []

    return [
        RetrievedChunk(
            chunk_id=chunk_id,
            text=text,
            scheme_name=meta["scheme_name"],
            category=meta["category"],
            source_url=meta["source_url"],
            fetched_at=meta["fetched_at"],
            score=score,
        )
        for chunk_id, text, meta, score in zip(
            result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
        )
    ]


def search(query: str, k: int = 4, scheme_filter: str | None = None) -> list[RetrievedChunk]:
    if scheme_filter is None:
        matched = find_scheme(query)
        scheme_filter = matched["name"] if matched else None

    where = {"scheme_name": scheme_filter} if scheme_filter else None
    return _run_query(query, k, where)


if __name__ == "__main__":
    # One hand-written query per PRD §6.3 factual question type, paired with
    # the scheme it should resolve to.
    sample_queries = [
        ("What is the expense ratio of HDFC Large Cap Fund?", "HDFC Large Cap Fund - Direct Growth"),
        ("What is the exit load for HDFC Flexi Cap Fund?", "HDFC Flexi Cap Fund - Direct Growth"),
        ("What is the minimum SIP for HDFC ELSS Tax Saver Fund?", "HDFC ELSS Tax Saver Fund - Direct Plan Growth"),
        ("What is the lock-in period for HDFC ELSS Tax Saver Fund?", "HDFC ELSS Tax Saver Fund - Direct Plan Growth"),
        ("What is the riskometer rating of HDFC Small Cap Fund?", "HDFC Small Cap Fund - Direct Growth"),
        ("What is the benchmark index of HDFC Balanced Advantage Fund?", "HDFC Balanced Advantage Fund - Direct Growth"),
        (
            "How do I download the capital gains statement for HDFC Large Cap Fund?",
            "HDFC Large Cap Fund - Direct Growth",
        ),
    ]

    def _report(label: str, results: list[RetrievedChunk], expected_scheme: str, query: str) -> None:
        top = results[0] if results else None
        status = "OK" if top and top.scheme_name == expected_scheme else "MISMATCH"
        print(f"[{status}] {query}")
        print(f"    top scheme: {top.scheme_name} (score={top.score:.4f})" if top else "    no results")

    print("=== With auto scheme-filter (find_scheme detects the named scheme) ===")
    for query, expected_scheme in sample_queries:
        _report("filtered", search(query, k=4), expected_scheme, query)

    print("\n=== Without scheme-filter (pure semantic similarity across all schemes) ===")
    for query, expected_scheme in sample_queries:
        _report("unfiltered", _run_query(query, k=4, where=None), expected_scheme, query)
