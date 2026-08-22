"""
DAAD PhD Germany scraper.
URL: https://www.daad.de/en/studying-in-germany/phd-studies-research/phd-germany/

The DAAD PhDGermany database uses an internal XHR API.
We target it directly with keyword filtering.
"""
from __future__ import annotations

import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.base import BaseScraper
from scraper.models import Offer

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.daad.de"
# Known API endpoint discovered via Network tab inspection
_API_URL = "https://www2.daad.de/deutschland/promotion/phd/de/suche/"
_SEARCH_PARAMS = {
    "q": "cloud distributed systems",
    "lang": "de",
    "country": "",
    "field": "",
}
_FALLBACK_URL = _BASE_URL + "/en/studying-in-germany/phd-studies-research/phd-germany/"


class DaadScraper(BaseScraper):
    source_name = "daad_phdgermany"

    def fetch(self) -> str:
        if not self.check_robots(_BASE_URL, "/en/"):
            return ""
        # Try the direct search page which may have filterable listing
        try:
            resp = self.get(_FALLBACK_URL)
            return resp.text
        except Exception as exc:
            logger.warning("[daad] Failed to fetch listing page: %s", exc)
            return ""

    def parse(self, raw: str) -> list[Offer]:
        if not raw:
            return []
        soup = BeautifulSoup(raw, "lxml")
        offers = []

        # DAAD page lists PhD positions in various card/article structures
        # Try multiple selectors for robustness
        cards = (
            soup.select("div.c-phd-result, article.phd-item, .phd-listing__item")
            or soup.find_all("div", class_=lambda c: c and "result" in c.lower())
        )

        if not cards:
            logger.warning(
                "[daad] No offer cards found in HTML — structure may have changed."
            )
            return []

        for card in cards:
            link = card.find("a", href=True)
            if not link:
                continue
            url = urljoin(_BASE_URL, link["href"])
            title_tag = card.find(["h2", "h3", "h4"])
            title = title_tag.get_text(strip=True) if title_tag else link.get_text(strip=True)
            if not title:
                continue

            institution_tag = card.find(class_=lambda c: c and any(
                kw in c.lower() for kw in ("institution", "university", "hochschule")
            ))
            institution = institution_tag.get_text(strip=True) if institution_tag else None

            funding_tag = card.find(class_=lambda c: c and "financ" in (c or "").lower())
            funding = funding_tag.get_text(strip=True) if funding_tag else None

            deadline_tag = card.find(class_=lambda c: c and "deadline" in (c or "").lower())
            deadline = deadline_tag.get_text(strip=True) if deadline_tag else None

            city_tag = card.find(class_=lambda c: c and any(
                k in (c or "").lower() for k in ("city", "location", "ort")
            ))
            location = city_tag.get_text(strip=True) if city_tag else None

            offers.append(Offer(
                source=self.source_name,
                title=title.strip(),
                institution=institution,
                url=url.strip(),
                country="DE",
                location=location,
                funding_type=funding,
                deadline=deadline,
            ))
        return offers
