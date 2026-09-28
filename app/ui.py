"""Phase 9 — Streamlit UI.

Chat UI over retrieval.pipeline.answer_query(). Chat history and the
"scheme currently being discussed" live only in st.session_state (in-memory,
per browser session) - nothing is written to disk, consistent with the
no-PII/no-storage constraint. Styling comes from .streamlit/config.toml
(native theming), not custom CSS.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

# streamlit run only puts this file's own directory on sys.path, not the
# project root, so the sibling `retrieval` package wouldn't otherwise import.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from retrieval.guardrails import GREETING_RESPONSE
from retrieval.pipeline import answer_query

SCHEMES = [
    "HDFC Large Cap Fund - Direct Growth",
    "HDFC Flexi Cap Fund - Direct Growth",
    "HDFC ELSS Tax Saver Fund - Direct Plan Growth",
    "HDFC Small Cap Fund - Direct Growth",
    "HDFC Balanced Advantage Fund - Direct Growth",
]
CATEGORIES = ["Large cap", "Flexi cap", "ELSS", "Small cap", "Balanced advantage"]

# Shown before any scheme has been discussed.
EXAMPLE_QUESTIONS = [
    "What is the expense ratio of HDFC Large Cap Fund?",
    "What is the lock-in period for HDFC ELSS Tax Saver Fund?",
    "What is the exit load for HDFC Flexi Cap Fund?",
]

# Once a scheme is in context, quick replies are short topic chips:
# (chip label, keyword meaning "this was just asked", question template).
FACT_TOPICS = [
    ("Expense ratio", "expense", "What is the expense ratio of {scheme}?"),
    ("Exit load", "exit load", "What is the exit load for {scheme}?"),
    ("Minimum SIP", "sip", "What is the minimum SIP for {scheme}?"),
    ("Riskometer", "risk", "What is the riskometer rating of {scheme}?"),
    ("Benchmark", "benchmark", "What is the benchmark index of {scheme}?"),
]
ELSS_TOPIC = ("Lock-in period", "lock", "What is the lock-in period for {scheme}?")

# Non-"answered" outcomes get a small badge so it's visually obvious *why*
# a question wasn't answered plainly, matching architecture.md's guardrail
# table (advice/performance refused, PII blocked, fact not in sources).
ACTION_BADGES = {
    "ADVICE_REFUSED": ("Not investment advice", "orange", ":material/info:"),
    "PERFORMANCE_REFUSED": ("Not investment advice", "orange", ":material/info:"),
    "PII_BLOCKED": ("Blocked - personal info detected", "red", ":material/block:"),
    "NOT_FOUND": ("Not in sources", "gray", ":material/search_off:"),
}

ASSISTANT_AVATAR = ":material/account_balance:"
TYPING_DELAY_SECONDS = 0.02


def _clear_chat() -> None:
    st.session_state.messages = []
    st.session_state.last_scheme = None


st.set_page_config(
    page_title="HDFC MF FAQ Assistant",
    page_icon=":material/account_balance:",
    layout="centered",
)

if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_scheme" not in st.session_state:
    st.session_state.last_scheme = None

with st.sidebar:
    st.header("About", icon=":material/info:")
    st.write(
        "Answers factual questions about 5 HDFC mutual fund schemes using only "
        "their official public pages. It doesn't give investment advice or "
        "compute/compare returns."
    )
    st.subheader("Schemes in scope", divider=False)
    for name in SCHEMES:
        st.caption(name)
    st.button(
        "Clear conversation",
        icon=":material/delete:",
        on_click=_clear_chat,
        width="stretch",
    )

header_col, restart_col = st.columns([5, 1], vertical_alignment="bottom")
with header_col:
    st.title("HDFC mutual fund FAQ assistant", icon=":material/account_balance:")
restart_slot = restart_col.container()

st.markdown(" ".join(f":blue-badge[{c}]" for c in CATEGORIES))
st.info("Facts-only. No investment advice.", icon=":material/verified:")


def _typewriter(text: str):
    for token in re.findall(r"\S+\s*", text):
        yield token
        time.sleep(TYPING_DELAY_SECONDS)


def _render_message(msg: dict, stream: bool = False) -> None:
    avatar = ASSISTANT_AVATAR if msg["role"] == "assistant" else None
    with st.chat_message(msg["role"], avatar=avatar):
        badge = ACTION_BADGES.get(msg.get("action"))
        if badge:
            label, color, icon = badge
            st.badge(label, icon=icon, color=color)
        if stream:
            st.write_stream(_typewriter(msg["text"]))
        else:
            st.markdown(msg["text"])
        if msg.get("citation_url"):
            st.markdown(f":material/link: [{msg['citation_url']}]({msg['citation_url']})")
        if msg.get("last_updated"):
            st.caption(f"Last updated from sources: {msg['last_updated']}")


def _answer_turn(query: str) -> None:
    user_message = {"role": "user", "text": query}
    _render_message(user_message)

    with st.spinner("Thinking..."):
        response = answer_query(query, scheme_hint=st.session_state.last_scheme)

    assistant_message = {
        "role": "assistant",
        "text": response.text,
        "citation_url": response.citation_url,
        "last_updated": response.last_updated,
        "action": response.action.value,
    }
    _render_message(assistant_message, stream=True)

    st.session_state.messages += [user_message, assistant_message]
    if response.scheme_name:
        st.session_state.last_scheme = response.scheme_name


def _suggestions() -> dict[str, str]:
    """Chip label -> the full question it sends."""
    scheme = st.session_state.last_scheme
    if not scheme:
        return {q: q for q in EXAMPLE_QUESTIONS}

    short_name = scheme.split(" - ")[0]
    topics = FACT_TOPICS + ([ELSS_TOPIC] if "ELSS" in scheme else [])
    last_user_text = next(
        (m["text"].lower() for m in reversed(st.session_state.messages) if m["role"] == "user"), ""
    )
    return {
        label: template.format(scheme=short_name)
        for label, keyword, template in topics
        if keyword not in last_user_text
    }


def _queue_suggestion(key: str, options: dict[str, str]) -> None:
    choice = st.session_state.get(key)
    if choice:
        st.session_state.pending_query = options[choice]


def _render_suggestions() -> None:
    options = _suggestions()
    if not options:
        return
    scheme = st.session_state.last_scheme
    st.caption(f"Ask more about {scheme.split(' - ')[0]}:" if scheme else "Try asking:")
    # The key changes every turn so each set of chips starts with nothing selected.
    key = f"suggestions_{len(st.session_state.messages)}"
    st.pills(
        "Suggested questions",
        list(options),
        key=key,
        label_visibility="collapsed",
        on_change=_queue_suggestion,
        args=(key, options),
    )


with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
    st.markdown(GREETING_RESPONSE)

for message in st.session_state.messages:
    _render_message(message)

typed_query = st.chat_input("Ask about expense ratio, exit load, minimum SIP, lock-in, riskometer, or benchmark...")
query = st.session_state.pop("pending_query", None) or typed_query
if query:
    _answer_turn(query)

# Filled after the turn is handled so it appears right after the first message.
with restart_slot:
    if st.session_state.messages:
        st.button("Start over", icon=":material/restart_alt:", on_click=_clear_chat, width="stretch")

_render_suggestions()
