"""Phase 8 — Query Pipeline.

Single entrypoint the UI (or any caller) uses: guardrails run first, and
only an in-scope, non-PII query proceeds to retrieval + composition. No
UI-framework imports here, so this stays reusable across front ends.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from retrieval.composer import compose
from retrieval.guardrails import GuardrailAction, route
from retrieval.retriever import search
from retrieval.scheme_lookup import find_scheme


class PipelineAction(str, Enum):
    PII_BLOCKED = "PII_BLOCKED"
    ADVICE_REFUSED = "ADVICE_REFUSED"
    PERFORMANCE_REFUSED = "PERFORMANCE_REFUSED"
    GREETING = "GREETING"
    ANSWERED = "ANSWERED"
    NOT_FOUND = "NOT_FOUND"


@dataclass
class Response:
    action: PipelineAction
    text: str
    citation_url: str | None = None
    last_updated: str | None = None
    scheme_name: str | None = None  # scheme this turn was about; callers pass it back as scheme_hint


_GUARDRAIL_TO_PIPELINE_ACTION = {
    GuardrailAction.PII_BLOCKED: PipelineAction.PII_BLOCKED,
    GuardrailAction.ADVICE_REFUSED: PipelineAction.ADVICE_REFUSED,
    GuardrailAction.PERFORMANCE_REFUSED: PipelineAction.PERFORMANCE_REFUSED,
    GuardrailAction.GREETING: PipelineAction.GREETING,
}


def answer_query(query: str, k: int = 4, scheme_hint: str | None = None) -> Response:
    """scheme_hint is the scheme from the previous turn, used only when the
    query itself doesn't name one (so "and its exit load?" follows up)."""
    guardrail_result = route(query, scheme_hint=scheme_hint)
    if guardrail_result.action == GuardrailAction.PII_BLOCKED:
        return Response(action=PipelineAction.PII_BLOCKED, text=guardrail_result.message)

    matched = find_scheme(query)
    scheme_name = matched["name"] if matched else scheme_hint

    if guardrail_result.action != GuardrailAction.PROCEED:
        return Response(
            action=_GUARDRAIL_TO_PIPELINE_ACTION[guardrail_result.action],
            text=guardrail_result.message,
            scheme_name=scheme_name,
        )

    effective_query = query if matched or not scheme_name else f"{query} ({scheme_name})"
    chunks = search(effective_query, k=k, scheme_filter=scheme_name)
    answer = compose(effective_query, chunks)
    if answer.not_found:
        return Response(action=PipelineAction.NOT_FOUND, text=answer.text, scheme_name=scheme_name)

    return Response(
        action=PipelineAction.ANSWERED,
        text=answer.text,
        citation_url=answer.citation_url,
        last_updated=answer.last_updated,
        scheme_name=scheme_name,
    )


if __name__ == "__main__":
    import os

    in_scope_queries = [
        "What is the expense ratio of HDFC Large Cap Fund?",
        "What is the exit load for HDFC Flexi Cap Fund?",
        "What is the minimum SIP for HDFC ELSS Tax Saver Fund?",
        "What is the lock-in period for HDFC ELSS Tax Saver Fund?",
        "What is the riskometer rating of HDFC Small Cap Fund?",
        "What is the benchmark index of HDFC Balanced Advantage Fund?",
        "How do I download the capital gains statement for HDFC Large Cap Fund?",
    ]
    advice_queries = [
        "Should I buy HDFC Large Cap Fund?",
        "Should I sell my HDFC ELSS units?",
        "Which fund is better, HDFC Large Cap or HDFC Flexi Cap?",
    ]
    performance_queries = [
        "What returns can I expect from HDFC Small Cap Fund?",
        "Compare the performance of HDFC Large Cap and HDFC Flexi Cap.",
        "What is the CAGR of HDFC ELSS Tax Saver Fund?",
    ]
    pii_queries = [
        "My PAN is ABCDE1234F, can you check my exit load?",
        "My email is test@example.com, what is the expense ratio?",
        "My phone number is 9876543210, please tell me the minimum SIP.",
    ]

    def _print(query: str, response: Response) -> None:
        print(f"[{response.action.value:20s}] {query}")
        print(f"    {response.text}")
        if response.citation_url:
            print(f"    citation: {response.citation_url}")
        if response.last_updated:
            print(f"    last_updated: {response.last_updated}")
        print()

    print("=== ADVICE (expect ADVICE_REFUSED) ===")
    for q in advice_queries:
        _print(q, answer_query(q))

    print("=== PERFORMANCE (expect PERFORMANCE_REFUSED) ===")
    for q in performance_queries:
        _print(q, answer_query(q))

    print("=== PII (expect PII_BLOCKED) ===")
    for q in pii_queries:
        _print(q, answer_query(q))

    print("=== IN-SCOPE (expect ANSWERED) ===")
    if not os.environ.get("GROQ_API_KEY"):
        print("GROQ_API_KEY not set - skipping live generation.")
        print("(Guardrail routing and retrieval for these queries are already covered above/in Phase 5-6 tests.)")
    else:
        for q in in_scope_queries:
            _print(q, answer_query(q))
