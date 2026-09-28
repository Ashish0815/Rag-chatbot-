"""Phase 3 — Chunker.

Splits each loaded Document into retrieval-sized chunks, propagating
scheme/source metadata onto every chunk.

The source pages are dense label/value fact pairs (e.g. "Expense ratio" on
one line, "1.03%" on the next) rather than long-form prose, so the primary
strategy is a recursive character splitter with a chunk size generous
enough (and enough overlap) that adjacent facts land in the same chunk. The
split function is swappable behind SPLIT_STRATEGY so a semantic splitter
can be substituted later without touching get_chunks() or its callers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from langchain_text_splitters import RecursiveCharacterTextSplitter

from ingestion.loader import Document, slug_from_url

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

_recursive_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
)


@dataclass
class Chunk:
    chunk_id: str
    text: str
    scheme_name: str
    category: str
    source_url: str
    fetched_at: str


def _split_recursive(text: str) -> list[str]:
    return _recursive_splitter.split_text(text)


SPLIT_STRATEGY: Callable[[str], list[str]] = _split_recursive


def get_chunks(document: Document) -> list[Chunk]:
    pieces = SPLIT_STRATEGY(document.raw_text)
    slug = slug_from_url(document.source_url)
    return [
        Chunk(
            chunk_id=f"{slug}::{i}",
            text=piece,
            scheme_name=document.scheme_name,
            category=document.category,
            source_url=document.source_url,
            fetched_at=document.fetched_at,
        )
        for i, piece in enumerate(pieces)
    ]


if __name__ == "__main__":
    from ingestion.loader import load_sources

    docs = load_sources()
    total_chunks = 0
    for doc in docs:
        chunks = get_chunks(doc)
        total_chunks += len(chunks)
        print(f"- {doc.scheme_name}: {len(chunks)} chunks")
        for c in chunks[:2]:
            print(f"  [{c.chunk_id}] {c.text[:120]!r}")
    print(f"\nTotal chunks across {len(docs)} document(s): {total_chunks}")
