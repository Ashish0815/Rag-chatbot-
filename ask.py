"""Manual interactive tester for the query pipeline (pre-UI).

Run with: python3 ask.py
Type a question, see the chatbot's answer. Type 'exit' or Ctrl+C to quit.
"""
from __future__ import annotations

from retrieval.pipeline import answer_query


def main() -> None:
    print("Mutual Fund FAQ Assistant (HDFC schemes) - facts-only, no investment advice.")
    print("Type a question, or 'exit' to quit.\n")
    while True:
        try:
            query = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not query:
            continue
        if query.lower() in {"exit", "quit"}:
            break

        response = answer_query(query)
        print(f"\nBot [{response.action.value}]: {response.text}")
        if response.citation_url:
            print(f"Source: {response.citation_url}")
        if response.last_updated:
            print(f"Last updated from sources: {response.last_updated}")
        print()


if __name__ == "__main__":
    main()
