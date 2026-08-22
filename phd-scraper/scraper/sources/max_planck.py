"""
Max Planck Society job board scraper.
URL: https://www.mpg.de/jobboard
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.base import BaseScraper
from scraper.models import Offer

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.mpg.de"
_SEARCH_URL = _BASE_URL + "/en/jobboard"
# Query params discovered by browser network inspection
_PARAMS = {
    "jobtype": "PhD+Position",
    "field": "Computer+Science",
}


class MaxPlanckScraper(BaseScraper):
    source_name = "max_planck"

    def fetch(self) -> str:
        if not self.check_robots(_BASE_URL, "/en/jobboard"):
            return ""
        try:
            resp = self.get(_SEARCH_URL, params=_PARAMS)
            return resp.text
        except Exception as exc:
            logger.warning("[max_planck] Failed to fetch job board: %s", exc)
            return ""

    def parse(self, raw: str) -> list[Offer]:
        if not raw:
            return []
        soup = BeautifulSoup(raw, "lxml")
        offers = []
        seen_urls: set[str] = set()

        cards = soup.select(
            "article.job-ad, div.job-item, li.job-listing, "
            ".jobad-item, .position-item"
        )
        if not cards:
            links = soup.find_all("a", href=re.compile(r"/en/jobboard/|/jobs/|/stellen/", re.I))
            cards = links

        if not cards:
            logger.warning(
                "[max_planck] No offer cards found in HTML — structure may have changed."
            )
            return []

        for card in cards:
            link = card if card.name == "a" else card.find("a", href=True)
            if not link:
                continue
            href = link.get("href", "")
            url = urljoin(_BASE_URL, href) if not href.startswith("http") else href
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

            inst_tag = card.find(class_=re.compile(r"institut|institute|mpi|mpl", re.I))
            institution = (
                inst_tag.get_text(strip=True) if inst_tag else "Max Planck Institute"
            )

            location_tag = card.find(class_=re.compile(r"location|city|ort|region", re.I))
            location = location_tag.get_text(strip=True) if location_tag else None

            deadline_tag = card.find(class_=re.compile(r"deadline|bewerbungsschluss", re.I))
            deadline = deadline_tag.get_text(strip=True) if deadline_tag else None

            offers.append(Offer(
                source=self.source_name,
                title=title.strip(),
                institution=institution,
                url=url.strip(),
                country="DE",
                location=location,
                deadline=deadline,
                funding_type="TV-L",
            ))
        return offers
