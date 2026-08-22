"""
Inria careers scraper.
URL: https://jobs.inria.fr/public/classic/fr/offres?filtre=doctorants

Inria's career portal is the most stable French source. The URL above
filters directly for PhD (doctorant) positions.
We first attempt to find an RSS feed; if unavailable, we parse the HTML listing.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.base import BaseScraper
from scraper.models import Offer

logger = logging.getLogger(__name__)

_BASE_URL = "https://jobs.inria.fr"
_LIST_URL = _BASE_URL + "/public/classic/fr/offres?filtre=doctorants"
_RSS_URL = _BASE_URL + "/public/classic/fr/offres/rss?filtre=doctorants"


class InriaScraper(BaseScraper):
    source_name = "inria"

    def fetch(self) -> str:
        if not self.check_robots(_BASE_URL, "/public/"):
            return ""
        # Try RSS first
        try:
            import feedparser
            resp = self.get(_RSS_URL)
            feed = feedparser.parse(resp.text)
            if feed.entries:
                logger.info("[inria] Using RSS feed (%d entries).", len(feed.entries))
                return resp.text  # raw RSS/XML
        except Exception as exc:
            logger.debug("[inria] RSS attempt failed: %s — falling back to HTML.", exc)

        resp = self.get(_LIST_URL)
        return resp.text

    def parse(self, raw: str) -> list[Offer]:
        if not raw:
            return []
        # Detect RSS vs HTML
        if raw.strip().startswith("<?xml") or "<rss" in raw[:200] or "<feed" in raw[:200]:
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
            location = _extract_city(summary)
            offers.append(Offer(
                source=self.source_name,
                title=title.strip(),
                url=url.strip(),
                country="FR",
                location=location,
                published_at=published[:10] if published and len(published) >= 10 else None,
                description=_strip_html(summary)[:500],
            ))
        return offers

    def _parse_html(self, raw: str) -> list[Offer]:
        soup = BeautifulSoup(raw, "lxml")
        offers = []
        # Inria portal uses article or li cards — try both
        cards = soup.select("article.offer, li.offer, div.offer-item, .job-offer")
        if not cards:
            # Broader fallback: any link whose href points to /public/classic/fr/offres/<id>
            cards = soup.find_all("a", href=re.compile(r"/public/classic/fr/offres/\d+"))
        if not cards:
            logger.warning(
                "[inria] Could not locate offer cards in HTML — structure may have changed."
            )
            return []

        for card in cards:
            tag = card if card.name != "a" else card
            link_tag = card if card.name == "a" else card.find("a", href=True)
            if not link_tag:
                continue
            href = link_tag.get("href", "")
            url = urljoin(_BASE_URL, href)

            title_tag = card.find(["h2", "h3", "h4", "span"], class_=re.compile(r"title|name", re.I))
            title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)

            city_tag = card.find(class_=re.compile(r"city|location|lieu", re.I))
            location = city_tag.get_text(strip=True) if city_tag else None

            team_tag = card.find(class_=re.compile(r"team|equipe|labo", re.I))
            lab = team_tag.get_text(strip=True) if team_tag else None

            date_tag = card.find(class_=re.compile(r"date|publi", re.I))
            published = date_tag.get_text(strip=True) if date_tag else None

            offers.append(Offer(
                source=self.source_name,
                title=title.strip(),
                url=url.strip(),
                country="FR",
                location=location,
                lab=lab,
                published_at=published,
                funding_type="Contrat doctoral",
            ))
        return offers


def _extract_city(text: str) -> str | None:
    m = re.search(r"(?:Localisation|Ville|City)\s*:\s*([^\n<,]+)", text, re.I)
    return m.group(1).strip() if m else None


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).strip()
