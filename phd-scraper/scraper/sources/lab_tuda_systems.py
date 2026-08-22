"""
TU Darmstadt Systems@TUDa (Istvan) lab scraper.
URL: https://www.informatik.tu-darmstadt.de/systems/systems_tuda/news/index.en.jsp

This page lists dated news entries including open positions formatted as:
  "Open Position: Research Assistant / PhD Student ..."
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.base import BaseScraper
from scraper.models import Offer

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.informatik.tu-darmstadt.de"
_NEWS_URL = (
    _BASE_URL
    + "/systems/systems_tuda/news/index.en.jsp"
)
_POSITION_RE = re.compile(
    r"\b(open position|phd student|research assistant|postdoc|opening|vacancy)\b",
    re.I,
)


class TudaSystemsScraper(BaseScraper):
    source_name = "lab_tuda_systems"

    def fetch(self) -> str:
        if not self.check_robots(_BASE_URL, "/systems/"):
            return ""
        try:
            resp = self.get(_NEWS_URL)
            return resp.text
        except Exception as exc:
            logger.warning("[tuda_systems] Failed to fetch news page: %s", exc)
            return ""

    def parse(self, raw: str) -> list[Offer]:
        if not raw:
            return []
        soup = BeautifulSoup(raw, "lxml")
        offers = []
        seen_urls: set[str] = set()

        # News entries are typically in <li>, <article>, or div.news-item
        entries = soup.select("li.news-item, article.news, div.news-entry, li, article")
        if not entries:
            logger.warning(
                "[tuda_systems] No news entries found — structure may have changed."
            )
            return []

        for entry in entries:
            text = entry.get_text(separator=" ", strip=True)
            if not _POSITION_RE.search(text):
                continue

            link = entry.find("a", href=True)
            url = urljoin(_BASE_URL, link["href"]) if link else _NEWS_URL
            if url in seen_urls:
                continue
            seen_urls.add(url)

            heading = entry.find(["h2", "h3", "h4", "strong"])
            title = heading.get_text(strip=True) if heading else text[:120]

            # Try to extract a date
            date_tag = entry.find(class_=re.compile(r"date|datum|zeit", re.I))
            date_str = date_tag.get_text(strip=True) if date_tag else None

            offers.append(Offer(
                source=self.source_name,
                title=title.strip(),
                institution="TU Darmstadt",
                lab="Systems@TUDa (Istvan)",
                url=url.strip(),
                country="DE",
                location="Darmstadt",
                published_at=date_str,
                funding_type="TV-L E13",
                description=text[:500],
            ))

        return offers
