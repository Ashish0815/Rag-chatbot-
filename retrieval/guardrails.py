"""Phase 5 — Guardrail Router.

Runs before any retrieval. Blocks queries containing PII and refuses
out-of-scope (advice/performance) questions with a fixed template, per
architecture.md §4. Nothing about a PII-flagged query is logged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from retrieval.scheme_lookup import find_scheme, scheme_by_name

Scope = Literal["in_scope", "advice", "performance", "greeting"]


class GuardrailAction(str, Enum):
    PII_BLOCKED = "PII_BLOCKED"
    ADVICE_REFUSED = "ADVICE_REFUSED"
    PERFORMANCE_REFUSED = "PERFORMANCE_REFUSED"
    GREETING = "GREETING"
    PROCEED = "PROCEED"


@dataclass
class GuardrailResult:
    action: GuardrailAction
    message: str | None = None  # fixed refusal text; None when action is PROCEED


# --- PII detection -----------------------------------------------------

PAN_PATTERN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+")
PHONE_PATTERN = re.compile(r"(?<!\d)(\+?91[\s-]?)?[6-9]\d{9}(?!\d)")
AADHAAR_PATTERN = re.compile(r"(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)")
ACCOUNT_NUMBER_PATTERN = re.compile(r"(?<!\d)\d{9,18}(?!\d)")
OTP_KEYWORD_PATTERN = re.compile(r"\botp\b", re.IGNORECASE)
OTP_DIGIT_PATTERN = re.compile(r"(?<!\d)\d{4,6}(?!\d)")


def contains_pii(query: str) -> bool:
    if PAN_PATTERN.search(query):
        return True
    if EMAIL_PATTERN.search(query):
        return True
    if AADHAAR_PATTERN.search(query):
        return True
    if ACCOUNT_NUMBER_PATTERN.search(query):
        return True
    if PHONE_PATTERN.search(query):
        return True
    if OTP_KEYWORD_PATTERN.search(query) and OTP_DIGIT_PATTERN.search(query):
        return True
    return False


# --- Scope classification -----------------------------------------------

ADVICE_KEYWORDS = [
    "should i buy",
    "should i sell",
    "should i invest",
    "should i choose",
    "should i pick",
    "should i go with",
    "worth buying",
    "worth investing",
    "is it worth it",
    "which fund is better",
    "which scheme is better",
    "which one is better",
    "which is better",
    "which fund should i",
    "which scheme should i",
    "best fund to invest",
    "best fund for",
    "recommend a fund",
    "recommend me",
    "good investment",
    "good fund to buy",
    "good idea to invest",
]

PERFORMANCE_KEYWORDS = [
    "compare returns",
    "compare performance",
    "compare funds",
    "how much will i earn",
    "how much will i make",
    "how much money will i get",
    "expected return",
    "future return",
    "past performance",
    "annualised return",
    "annualized return",
    "rate of return",
]

PERFORMANCE_PATTERN = re.compile(r"\b(returns?|cagr|performance|profit)\b", re.IGNORECASE)

# Matches when the *whole* message is just a greeting/small-talk (optionally
# with punctuation) - e.g. "Hi", "hello there". A word-boundary/full-match
# pattern is required here (not a plain substring check like the keyword
# lists above) because short words like "hi" or "hey" are also substrings of
# unrelated words ("which", "this", "hey" inside "they're", etc.).
GREETING_PATTERN = re.compile(
    r"^\s*(hi|hey|hello|hiya|yo|howdy)(\s+(there|everyone|team|folks))?[\s!.,?]*$"
    r"|^\s*(greetings|good morning|good afternoon|good evening|how are you|what'?s up|sup)[\s!.,?]*$",
    re.IGNORECASE,
)

# Meta questions about the assistant itself, e.g. "what can you do?". These
# are full phrases, so a substring check (like ADVICE/PERFORMANCE_KEYWORDS)
# is safe - they don't collide with real factual questions.
HELP_KEYWORDS = [
    "what can you do",
    "what can you help",
    "what do you do",
    "what options",
    "what questions can",
    "what can i ask",
    "what can this",
    "how does this work",
    "who are you",
    "what is this bot",
    "what is this assistant",
    "help me",
    "need help",
    "what should i ask",
]


def classify_scope(query: str) -> Scope:
    text = query.lower().strip()
    if GREETING_PATTERN.match(text) or any(keyword in text for keyword in HELP_KEYWORDS):
        return "greeting"
    if any(keyword in text for keyword in ADVICE_KEYWORDS):
        return "advice"
    if PERFORMANCE_PATTERN.search(text) or any(keyword in text for keyword in PERFORMANCE_KEYWORDS):
        return "performance"
    return "in_scope"


# --- Fixed response templates (architecture.md §4) -----------------------

PII_DECLINE_MESSAGE = (
    "I can't process that message because it looks like it contains personal information "
    "(such as a PAN, Aadhaar, account number, OTP, email, or phone number). Please ask your "
    "question again without sharing that information."
)

EDUCATIONAL_LINK = "https://www.amfiindia.com/"
ADVICE_REFUSAL_MESSAGE = (
    "I can only share factual scheme details, not investment advice or recommendations. "
    f"For general guidance on evaluating mutual funds, see: {EDUCATIONAL_LINK}"
)


def _performance_refusal_message(query: str, scheme_hint: str | None = None) -> str:
    matched = find_scheme(query) or (scheme_by_name(scheme_hint) if scheme_hint else None)
    link = matched["url"] if matched else EDUCATIONAL_LINK
    return (
        "I don't compute or compare fund returns or performance. "
        f"Please check the official scheme page for that data: {link}"
    )


GREETING_RESPONSE = (
    "Hi! I'm a facts-only assistant for 5 HDFC mutual fund schemes (Large Cap, Flexi Cap, ELSS, "
    "Small Cap, Balanced Advantage). Ask me about expense ratio, exit load, minimum SIP, ELSS "
    "lock-in, riskometer rating, or benchmark index for any of these schemes. I don't give "
    "investment advice or compute/compare returns."
)


# --- Router ---------------------------------------------------------------


def route(query: str, scheme_hint: str | None = None) -> GuardrailResult:
    if contains_pii(query):
        return GuardrailResult(GuardrailAction.PII_BLOCKED, PII_DECLINE_MESSAGE)

    scope = classify_scope(query)
    if scope == "greeting":
        return GuardrailResult(GuardrailAction.GREETING, GREETING_RESPONSE)
    if scope == "advice":
        return GuardrailResult(GuardrailAction.ADVICE_REFUSED, ADVICE_REFUSAL_MESSAGE)
    if scope == "performance":
        return GuardrailResult(
            GuardrailAction.PERFORMANCE_REFUSED, _performance_refusal_message(query, scheme_hint)
        )

    return GuardrailResult(GuardrailAction.PROCEED, None)


if __name__ == "__main__":
    in_scope_queries = [
        "What is the expense ratio of HDFC Large Cap Fund?",
        "What is the exit load for HDFC Flexi Cap Fund?",
        "What is the minimum SIP amount for HDFC ELSS Tax Saver Fund?",
        "What is the lock-in period for HDFC ELSS Tax Saver Fund?",
        "What is the riskometer rating of HDFC Small Cap Fund?",
        "What is the benchmark index for HDFC Balanced Advantage Fund?",
        "How do I download the capital gains statement for my HDFC mutual fund?",
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
        "My Aadhaar number is 1234 5678 9012.",
        "My OTP is 483920, please confirm my order.",
    ]
    greeting_queries = [
        "Hi",
        "hello!",
        "Hey there",
        "What can you help with?",
        "What options are there?",
        "who are you?",
    ]

    for label, queries in [
        ("IN-SCOPE (expect PROCEED)", in_scope_queries),
        ("ADVICE (expect ADVICE_REFUSED)", advice_queries),
        ("PERFORMANCE (expect PERFORMANCE_REFUSED)", performance_queries),
        ("PII (expect PII_BLOCKED)", pii_queries),
        ("GREETING/HELP (expect GREETING)", greeting_queries),
    ]:
        print(f"\n=== {label} ===")
        for q in queries:
            result = route(q)
            print(f"  [{result.action.value:20s}] {q}")
