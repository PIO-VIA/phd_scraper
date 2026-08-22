"""
ADUM scraper — French doctoral school thesis portal.
URL: https://adum.fr

ADUM publishes PhD subjects from French doctoral schools. It has two peaks per
year (mid-March and September). If the portal requires authentication for search,
this scraper will detect it and warn rather than crash.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.base import BaseScraper
from scraper.models import Offer

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.adum.fr"
# Public search URL for computer science subjects
_SEARCH_URL = _BASE_URL + "/script/offres.pl?site=adum&ListMotCle=cloud+distributed+systems"


class AdumScraper(BaseScraper):
    source_name = "adum"

    def fetch(self) -> str:
        if not self.check_robots(_BASE_URL, "/script/"):
            return ""
        try:
            resp = self.get(_SEARCH_URL)
            # Detect auth wall
            if "login" in resp.url.path.lower() or "connexion" in resp.text.lower()[:200]:
                logger.warning(
                    "[adum] Authentication required — cannot scrape automatically. "
                    "Consult https://adum.fr manually."
                )
                return ""
            return resp.text
        except Exception as exc:
            logger.warning("[adum] Failed to fetch: %s", exc)
            return ""

    def parse(self, raw: str) -> list[Offer]:
        if not raw:
            return []
        soup = BeautifulSoup(raw, "lxml")
        offers = []
        seen_urls: set[str] = set()

        cards = soup.select("div.these, article.offer, tr.sujet, .subject-item")
        if not cards:
            links = soup.find_all("a", href=re.compile(r"/script/|/offre/|/sujet/", re.I))
            cards = links

        if not cards:
            logger.warning(
                "[adum] No thesis listings found — either no offers or structure changed."
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

            title_tag = card.find(["h2", "h3", "h4", "strong"]) if card.name != "a" else None
            title = (
                title_tag.get_text(strip=True)
                if title_tag
                else link.get_text(strip=True)
            )
            if not title:
                continue

            inst_tag = card.find(class_=re.compile(r"etablissement|univ|lab", re.I))
            institution = inst_tag.get_text(strip=True) if inst_tag else None

            prof_tag = card.find(class_=re.compile(r"directeur|prof|encadrant", re.I))
            professor = prof_tag.get_text(strip=True) if prof_tag else None

            offers.append(Offer(
                source=self.source_name,
                title=title.strip(),
                institution=institution,
                professor=professor,
                url=url.strip(),
                country="FR",
                funding_type="Contrat doctoral",
            ))
        return offers
