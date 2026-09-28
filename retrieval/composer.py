"""Phase 7 — Answer Composer.

Turns retrieved chunks into a grounded, constrained answer with exactly one
citation. The LLM (Groq-hosted Llama 3.3) only ever sees the retrieved
context and a strict system prompt — it never computes returns, gives
advice, or answers beyond what's in the chunks. Citation and "Last updated"
are attached deterministically afterwards, not left to the model.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv

from retrieval.retriever import RetrievedChunk

load_dotenv()

MODEL_NAME = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
MAX_ANSWER_TOKENS = 200

# Chroma L2 distance for the top hit. Empirically, genuinely off-topic
# queries (weather, sports) score >1.3 while every on-topic query -
# whether or not the specific fact is present in the chunk - scores well
# below that. So this threshold only catches "nothing relevant retrieved
# at all"; whether the *specific* fact is present is left to the LLM's
# context-only instruction below (see NOT_FOUND_TEXT).
MAX_RELEVANT_DISTANCE = 1.3

NOT_FOUND_TEXT = "I don't have that fact in my sources."

SYSTEM_PROMPT = f"""You are a factual assistant for a small set of HDFC mutual fund schemes.
Answer ONLY using the context chunks provided in the user message - never use outside knowledge.

Rules:
- If the answer is not present in the context, reply with exactly: "{NOT_FOUND_TEXT}"
- Never mention, compute, or compare investment returns, performance, or CAGR.
- Never give investment advice, opinions, or recommendations.
- Answer in at most 3 sentences, factual and concise.
- Do not include any links, citations, or dates yourself - those are added separately."""


@dataclass
class Answer:
    text: str
    citation_url: str | None
    last_updated: str | None
    not_found: bool = False


def _build_context(chunks: list[RetrievedChunk]) -> str:
    return "\n\n".join(f"[{c.scheme_name}]\n{c.text}" for c in chunks)


def _enforce_sentence_limit(text: str, max_sentences: int = 3) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(sentences[:max_sentences]).strip()


def _call_llm(query: str, context: str) -> str:
    from groq import Groq

    client = Groq()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        max_tokens=MAX_ANSWER_TOKENS,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
        ],
    )
    return (response.choices[0].message.content or "").strip()


def compose(query: str, chunks: list[RetrievedChunk]) -> Answer:
    if not chunks or chunks[0].score > MAX_RELEVANT_DISTANCE:
        return Answer(text=NOT_FOUND_TEXT, citation_url=None, last_updated=None, not_found=True)

    top_chunk = chunks[0]
    context = _build_context(chunks)
    raw_answer = _call_llm(query, context)
    answer_text = _enforce_sentence_limit(raw_answer)

    if answer_text.strip().rstrip(".") == NOT_FOUND_TEXT.rstrip("."):
        return Answer(text=NOT_FOUND_TEXT, citation_url=None, last_updated=None, not_found=True)

    return Answer(
        text=answer_text,
        citation_url=top_chunk.source_url,
        last_updated=top_chunk.fetched_at,
        not_found=False,
    )


def format_for_display(answer: Answer) -> str:
    if answer.not_found:
        return answer.text
    return f"{answer.text}\nSource: {answer.citation_url}\nLast updated from sources: {answer.last_updated}"


if __name__ == "__main__":
    from retrieval.retriever import search

    sample_queries = [
        "What is the expense ratio of HDFC Large Cap Fund?",
        "What is the exit load for HDFC Flexi Cap Fund?",
        "What is the minimum SIP for HDFC ELSS Tax Saver Fund?",
        "What is the lock-in period for HDFC ELSS Tax Saver Fund?",
        "What is the riskometer rating of HDFC Small Cap Fund?",
        "What is the benchmark index of HDFC Balanced Advantage Fund?",
        "How do I download the capital gains statement for HDFC Large Cap Fund?",
    ]

    if not os.environ.get("GROQ_API_KEY"):
        print("GROQ_API_KEY not set - skipping live LLM calls.")
        print("Add it to a .env file (see .env.example) to test compose() end-to-end.")
    else:
        for query in sample_queries:
            chunks = search(query, k=4)
            answer = compose(query, chunks)
            print(f"Q: {query}")
            print(format_for_display(answer))
            print()
