"""Phase 2 — Loader.

Fetches the public scheme pages listed in config/sources.yaml and extracts
their main content text, stripped of site navigation/footer boilerplate.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup

RAW_DATA_DIR = Path("data/raw")

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
REQUEST_TIMEOUT_SECONDS = 15

# Groww's mutual fund pages are a single content column sandwiched between a
# large mega-menu (before the <h1> scheme name) and a site-wide footer (which
# always starts with one of these lines). Slicing the flattened body text
# between those two anchors drops the boilerplate without depending on
# hashed CSS class names, which change across deploys.
FOOTER_START_MARKERS = {"contact us", "download the app"}


@dataclass
class Document:
    scheme_name: str
    category: str
    source_url: str
    fetched_at: str
    raw_text: str


def _extract_main_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    h1 = soup.find("h1")
    body = soup.find("body")
    if body is None:
        return ""

    lines = [line for line in body.get_text(separator="\n", strip=True).split("\n") if line]

    start_idx = 0
    if h1 is not None:
        h1_text = h1.get_text(strip=True)
        for i, line in enumerate(lines):
            if line == h1_text:
                start_idx = i
                break

    end_idx = len(lines)
    for i in range(start_idx, len(lines)):
        if lines[i].strip().lower() in FOOTER_START_MARKERS:
            end_idx = i
            break

    return "\n".join(lines[start_idx:end_idx])


def _fetch_scheme_document(scheme: dict) -> Document | None:
    url = scheme["url"]
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[loader] SKIP {url}: fetch failed ({exc})", file=sys.stderr)
        return None

    raw_text = _extract_main_text(response.text)
    if not raw_text:
        print(f"[loader] SKIP {url}: no extractable content", file=sys.stderr)
        return None

    return Document(
        scheme_name=scheme["name"],
        category=scheme["category"],
        source_url=url,
        fetched_at=date.today().isoformat(),
        raw_text=raw_text,
    )


def load_sources(config_path: str | Path = "config/sources.yaml") -> list[Document]:
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    documents: list[Document] = []
    for scheme in config["schemes"]:
        document = _fetch_scheme_document(scheme)
        if document is not None:
            documents.append(document)
    return documents


def slug_from_url(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def save_raw_documents(documents: list[Document], out_dir: str | Path = RAW_DATA_DIR) -> None:
    """Persist each fetched Document to data/raw/<scheme-slug>.json for inspection/reuse."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    for doc in documents:
        file_path = out_path / f"{slug_from_url(doc.source_url)}.json"
        file_path.write_text(json.dumps(asdict(doc), indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    docs = load_sources()
    save_raw_documents(docs)
    print(f"Loaded {len(docs)} document(s), saved raw text to {RAW_DATA_DIR}/\n")
    for doc in docs:
        print(f"- {doc.scheme_name} [{doc.category}]")
        print(f"  source_url:  {doc.source_url}")
        print(f"  fetched_at:  {doc.fetched_at}")
        print(f"  text length: {len(doc.raw_text)} chars")
        print(f"  preview:     {doc.raw_text[:150]!r}")
        print()
