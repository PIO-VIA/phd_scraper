"""
Fraunhofer Gesellschaft jobs scraper.
Portals: https://www.fraunhofer.de/en/jobs-and-career/jobsearch.html
         https://jobs.fraunhofer.de
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.base import BaseScraper
from scraper.models import Offer

logger = logging.getLogger(__name__)

_BASE_URL = "https://jobs.fraunhofer.de"
# Search for PhD/Doktorand positions in systems/cloud topics
_SEARCH_URLS = [
    _BASE_URL + "/jobboard/search?q=Doktorand+cloud&lang=en",
    _BASE_URL + "/jobboard/search?q=Doktorand+distributed+systems&lang=en",
    _BASE_URL + "/jobboard/search?q=PhD+cloud+computing&lang=en",
]


class FraunhoferScraper(BaseScraper):
    source_name = "fraunhofer"

    def fetch(self) -> list[str]:
        if not self.check_robots(_BASE_URL, "/jobboard/"):
            return []
        pages: list[str] = []
        for url in _SEARCH_URLS:
            try:
                resp = self.get(url)
                pages.append(resp.text)
                self.sleep()
            except Exception as exc:
                logger.warning("[fraunhofer] Failed to fetch %s: %s", url, exc)
        return pages

    def parse(self, raw: list[str]) -> list[Offer]:
        seen_urls: set[str] = set()
        offers: list[Offer] = []
        for html in raw:
            if not html:
                continue
            soup = BeautifulSoup(html, "lxml")
            cards = soup.select(
                "article.job, div.job-item, li.job-result, "
                ".jobBoard-item, .vacancies-item"
            )
            if not cards:
                links = soup.find_all("a", href=re.compile(r"/job/|/stelle/|/jobdetail/", re.I))
                cards = links

            if not cards:
                logger.warning(
                    "[fraunhofer] No offer cards found — structure may have changed."
                )
                continue

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

                # Institute extraction from card text
                inst_tag = card.find(class_=re.compile(r"institut|institute|employer", re.I))
                institution = inst_tag.get_text(strip=True) if inst_tag else "Fraunhofer"

                location_tag = card.find(class_=re.compile(r"location|city|ort", re.I))
                location = location_tag.get_text(strip=True) if location_tag else None

                offers.append(Offer(
                    source=self.source_name,
                    title=title.strip(),
                    institution=institution,
                    url=url.strip(),
                    country="DE",
                    location=location,
                    funding_type="TV-L",
                ))
        return offers
