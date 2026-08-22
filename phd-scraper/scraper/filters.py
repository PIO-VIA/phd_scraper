"""
Keyword-based filtering for PhD offers.
Reads include/exclude keywords from config/keywords.yaml.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from scraper.models import Offer

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = Path(__file__).parent.parent / "config" / "keywords.yaml"


def load_keywords(config_path: str | Path | None = None) -> dict[str, list[str]]:
    """Load include/exclude keywords from YAML. Returns {'include': [...], 'exclude': [...]}."""
    path = Path(config_path or _DEFAULT_CONFIG)
    if not path.exists():
        logger.warning("Keywords config not found at %s — no filtering applied.", path)
        return {"include": [], "exclude": []}
    with path.open(encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}
    return {
        "include": [kw.lower() for kw in data.get("include", [])],
        "exclude": [kw.lower() for kw in data.get("exclude", [])],
    }


def _normalize(text: str) -> str:
    return text.lower()


def _find_hits(text: str, keywords: list[str]) -> list[str]:
    """Return the list of keywords found in text (case-insensitive)."""
    norm = _normalize(text)
    return [kw for kw in keywords if kw in norm]


def matches(offer: Offer, keywords: dict[str, list[str]]) -> tuple[bool, list[str]]:
    """
    Determine if an offer matches the keyword filter.

    Returns (is_match, matched_keywords).
    An offer matches if:
      - At least one include keyword is found in title or description.
      - No exclude keyword is found.
    """
    haystack_parts = [offer.title or ""]
    if offer.description:
        haystack_parts.append(offer.description)
    if offer.lab:
        haystack_parts.append(offer.lab)
    haystack = " ".join(haystack_parts)

    include_hits = _find_hits(haystack, keywords.get("include", []))
    exclude_hits = _find_hits(haystack, keywords.get("exclude", []))

    if exclude_hits:
        logger.debug(
            "Offer excluded (matched exclude keywords %s): %s",
            exclude_hits,
            offer.title,
        )
        return False, []

    if not include_hits:
        logger.debug("Offer skipped (no include keyword matched): %s", offer.title)
        return False, []

    return True, include_hits


def filter_offers(
    offers: list[Offer],
    keywords: dict[str, list[str]] | None = None,
    config_path: str | Path | None = None,
) -> list[Offer]:
    """
    Filter a list of offers by keywords.
    Sets `keywords_hit` on each matching offer before returning it.
    """
    if keywords is None:
        keywords = load_keywords(config_path)

    if not keywords.get("include"):
        logger.warning("No include keywords configured — returning all offers unfiltered.")
        return offers

    matched: list[Offer] = []
    for offer in offers:
        is_match, hits = matches(offer, keywords)
        if is_match:
            offer = offer.model_copy(update={"keywords_hit": ", ".join(hits)})
            matched.append(offer)

    logger.info(
        "Filtering: %d/%d offers matched keyword criteria.",
        len(matched), len(offers),
    )
    return matched
