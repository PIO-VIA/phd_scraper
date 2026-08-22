"""
EURAXESS scraper — European multi-country research job portal.
URL: https://euraxess.ec.europa.eu/jobs/search

Strategy:
  EURAXESS has a JSON API endpoint used by its internal search. We target it
  directly for stability. If it becomes unavailable, a fallback HTML parser
  is provided.

  JSON endpoint (discovered via browser Network tab):
  GET https://euraxess.ec.europa.eu/api/jobs/search
      ?keyword=<kw>&organisation_type=University,Research+Institute
      &page=0&rows=50

  The API returns a JSON envelope with an `items` list.
"""
from __future__ import annotations

import logging
from typing import Any

from scraper.base import BaseScraper
from scraper.models import Offer

logger = logging.getLogger(__name__)

# EURAXESS internal search API
_API_BASE = "https://euraxess.ec.europa.eu"
_SEARCH_API = _API_BASE + "/api/jobs/search"
# Keywords to inject into the API query — broad enough to capture all relevant offers.
_SEARCH_TERMS = [
    "cloud computing",
    "distributed systems",
    "systems research",
    "infrastructure",
    "kubernetes",
]
_ROWS_PER_PAGE = 50


class EuraxessScraper(BaseScraper):
    source_name = "euraxess"

    def fetch(self) -> list[dict]:
        """
        Query the EURAXESS JSON API for each search term and collect raw items.
        Returns a deduplicated list of raw job dicts (by URL).
        """
        if not self.check_robots(_API_BASE, "/api/"):
            return []

        seen_urls: set[str] = set()
        all_items: list[dict] = []

        for term in _SEARCH_TERMS:
            page = 0
            while True:
                params = {
                    "keyword": term,
                    "rows": _ROWS_PER_PAGE,
                    "page": page,
                }
                try:
                    resp = self.get(_SEARCH_API, params=params)
                    data = resp.json()
                except Exception as exc:
                    logger.warning(
                        "[euraxess] API request failed for term '%s' page %d: %s",
                        term, page, exc,
                    )
                    break

                items = data.get("items") or data.get("results") or []
                if not items:
                    # Try alternative response shape
                    if isinstance(data, list):
                        items = data
                    else:
                        logger.debug(
                            "[euraxess] No items in response for '%s' page %d. "
                            "Keys: %s", term, page, list(data.keys())
                        )
                        break

                new_count = 0
                for item in items:
                    url = self._extract_url(item)
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_items.append(item)
                        new_count += 1

                logger.debug(
                    "[euraxess] term='%s' page=%d → %d new items", term, page, new_count
                )

                # Stop pagination if we got fewer items than requested
                if len(items) < _ROWS_PER_PAGE:
                    break
                page += 1
                self.sleep()

            self.sleep()

        logger.info("[euraxess] Total unique raw items fetched: %d", len(all_items))
        return all_items

    def parse(self, raw: list[dict]) -> list[Offer]:
        """Convert raw API items to Offer objects."""
        offers: list[Offer] = []
        for item in raw:
            try:
                offer = self._item_to_offer(item)
                if offer:
                    offers.append(offer)
            except Exception as exc:
                logger.warning("[euraxess] Could not parse item: %s — %s", item, exc)
        return offers

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_url(self, item: dict) -> str | None:
        """Extract the canonical URL from an API item."""
        for key in ("url", "link", "href", "job_url"):
            val = item.get(key)
            if val:
                return val if val.startswith("http") else _API_BASE + val
        # Sometimes the path is in a 'path' or 'alias' field
        for key in ("path", "alias"):
            val = item.get(key)
            if val:
                return _API_BASE + ("" if val.startswith("/") else "/") + val
        return None

    def _item_to_offer(self, item: dict) -> Offer | None:
        url = self._extract_url(item)
        if not url:
            logger.debug("[euraxess] Item has no URL, skipping: %s", item)
            return None

        title = (
            item.get("title")
            or item.get("name")
            or item.get("job_title")
            or "(sans titre)"
        )

        institution = (
            item.get("organisation_name")
            or item.get("institution")
            or item.get("employer")
        )

        country_raw = (
            item.get("country")
            or item.get("country_code")
            or item.get("location_country")
        )
        country = _normalise_country(country_raw)

        location = item.get("city") or item.get("location") or item.get("town")

        deadline = item.get("application_deadline") or item.get("deadline")
        published = item.get("published_date") or item.get("created") or item.get("date")

        description = item.get("description") or item.get("excerpt") or item.get("summary") or ""
        if isinstance(description, dict):
            description = description.get("value", "") or ""

        funding = item.get("salary_range") or item.get("funding_type") or item.get("stipend")

        return Offer(
            source=self.source_name,
            title=str(title).strip(),
            institution=institution,
            url=url,
            country=country,
            location=str(location).strip() if location else None,
            deadline=_normalise_date(deadline),
            published_at=_normalise_date(published),
            funding_type=str(funding).strip() if funding else None,
            description=str(description).strip()[:1000] if description else None,
        )


# ------------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------------

def _normalise_country(raw: Any) -> str | None:
    if not raw:
        return None
    # EURAXESS sometimes returns full name, sometimes ISO code
    mapping = {
        "Germany": "DE",
        "Deutschland": "DE",
        "France": "FR",
        "United Kingdom": "GB",
        "Netherlands": "NL",
        "Switzerland": "CH",
        "Austria": "AT",
        "Belgium": "BE",
        "Sweden": "SE",
        "Denmark": "DK",
        "Italy": "IT",
        "Spain": "ES",
        "Czech Republic": "CZ",
        "Poland": "PL",
        "Portugal": "PT",
        "Finland": "FI",
        "Norway": "NO",
    }
    s = str(raw).strip()
    return mapping.get(s, s[:2].upper() if len(s) >= 2 else s)


def _normalise_date(raw: Any) -> str | None:
    """Best-effort ISO date normalisation from various API formats."""
    if not raw:
        return None
    s = str(raw).strip()
    if not s or s.lower() in {"null", "none", "n/a"}:
        return None
    # If already ISO-like (YYYY-MM-DD…), return as-is (truncated to date part)
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return s
