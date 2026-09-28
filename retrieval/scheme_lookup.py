"""Shared helper: detect which configured scheme (if any) a query mentions.

Used by both the guardrail router (to link a performance refusal to the
right scheme page) and the retriever (to filter ChromaDB results to the
right scheme).
"""
from __future__ import annotations

from functools import lru_cache

import yaml


@lru_cache(maxsize=1)
def _load_sources_config(config_path: str = "config/sources.yaml") -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _category_core(category: str) -> str:
    """Category minus any parenthetical qualifier, e.g. 'Balanced Advantage (Hybrid)' -> 'balanced advantage'."""
    return category.split("(")[0].strip().lower()


def scheme_by_name(name: str, config_path: str = "config/sources.yaml") -> dict | None:
    try:
        config = _load_sources_config(config_path)
    except FileNotFoundError:
        return None
    return next((s for s in config.get("schemes", []) if s["name"] == name), None)


def find_scheme(query: str, config_path: str = "config/sources.yaml") -> dict | None:
    """Return the {category, name, url} dict of the first scheme mentioned in query, else None."""
    try:
        config = _load_sources_config(config_path)
    except FileNotFoundError:
        return None

    text = query.lower()
    for scheme in config.get("schemes", []):
        if scheme["name"].lower() in text:
            return scheme
        if scheme["category"].lower() in text:
            return scheme
        if _category_core(scheme["category"]) in text:
            return scheme
    return None
