"""
CampusFrance doctorat offers scraper.
URL: https://doctorat.campusfrance.org/phd/offers
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.base import BaseScraper
from scraper.models import Offer

logger = logging.getLogger(__name__)

_BASE_URL = "https://doctorat.campusfrance.org"
_LIST_URL = _BASE_URL + "/phd/offers"
_RSS_CANDIDATES = [
    _BASE_URL + "/phd/offers/rss",
    _BASE_URL + "/rss/offers.xml",
    _BASE_URL + "/phd/offers.xml",
]


class CampusFranceScraper(BaseScraper):
    source_name = "campusfrance"

    def fetch(self) -> str:
        if not self.check_robots(_BASE_URL, "/phd/"):
            return ""
        # Try RSS/XML endpoints first
        for rss_url in _RSS_CANDIDATES:
            try:
                resp = self.get(rss_url)
                ct = resp.headers.get("content-type", "")
                if "xml" in ct or resp.text.strip().startswith("<?xml"):
                    logger.info("[campusfrance] Found XML/RSS feed at %s", rss_url)
                    return resp.text
            except Exception:
                pass

        # Fallback to HTML
        try:
            resp = self.get(_LIST_URL)
            return resp.text
        except Exception as exc:
            logger.warning("[campusfrance] Failed to fetch: %s", exc)
            return ""

    def parse(self, raw: str) -> list[Offer]:
        if not raw:
            return []
        if raw.strip().startswith("<?xml") or "<rss" in raw[:300] or "<feed" in raw[:300]:
            return self._parse_rss(raw)
        return self._parse_html(raw)

    def _parse_rss(self, raw: str) -> list[Offer]:
        import feedparser
        feed = feedparser.parse(raw)
        offers = []
        for entry in feed.entries:
            url = entry.get("link", "")
            if not url:
                continue
            title = entry.get("title", "(sans titre)")
            summary = entry.get("summary", "")
            published = entry.get("published", "")
            offers.append(Offer(
                source=self.source_name,
                title=title.strip(),
                url=url.strip(),
                country="FR",
                published_at=published[:10] if len(published) >= 10 else None,
                description=re.sub(r"<[^>]+>", " ", summary)[:500],
                funding_type="Contrat doctoral",
            ))
        return offers

    def _parse_html(self, raw: str) -> list[Offer]:
        soup = BeautifulSoup(raw, "lxml")
        offers = []
        seen_urls: set[str] = set()

        cards = soup.select("article, .offer-card, .thesis-item, li.phd-offer")
        if not cards:
            links = soup.find_all("a", href=re.compile(r"/phd/offer/|/offre/", re.I))
            cards = links

        if not cards:
            logger.warning(
                "[campusfrance] No offer cards found — structure may have changed."
            )
            return []

        for card in cards:
            link = card if card.name == "a" else card.find("a", href=True)
            if not link:
                continue
            url = urljoin(_BASE_URL, link.get("href", ""))
            if url in seen_urls:
                continue
            seen_urls.add(url)

            title_tag = card.find(["h2", "h3", "h4"]) if card.name != "a" else None
            title = (
                title_tag.get_text(strip=True)
                if title_tag
                else link.get_text(strip=True)
            )
            if not title:
                continue

            offers.append(Offer(
                source=self.source_name,
                title=title.strip(),
                url=url.strip(),
                country="FR",
                funding_type="Contrat doctoral",
            ))
        return offers
