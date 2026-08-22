"""
RWTH Aachen COMSYS (Wehrle) lab scraper.
URL: https://www.comsys.rwth-aachen.de/

Checks for a /jobs/ or /career/ page first; falls back to homepage.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.base import BaseScraper
from scraper.models import Offer

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.comsys.rwth-aachen.de"
_CANDIDATE_PATHS = ["/jobs/", "/career/", "/karriere/", "/openings/", "/positions/", "/"]
_POSITION_RE = re.compile(
    r"\b(phd|open position|postdoc|research assistant|vacancy|doctoral|opening)\b",
    re.I,
)


class RwthComSysScraper(BaseScraper):
    source_name = "lab_rwth_comsys"

    def fetch(self) -> tuple[str, str]:
        """Returns (html, page_url) of the first path that loads successfully."""
        if not self.check_robots(_BASE_URL, "/"):
            return "", _BASE_URL
        for path in _CANDIDATE_PATHS:
            url = _BASE_URL + path
            try:
                resp = self.get(url)
                if resp.status_code == 200:
                    logger.info("[rwth_comsys] Fetching from %s", url)
                    return resp.text, url
            except Exception:
                pass
            self.sleep(0.5)
        logger.warning("[rwth_comsys] Could not load any candidate page.")
        return "", _BASE_URL

    def parse(self, raw: tuple[str, str]) -> list[Offer]:
        html, page_url = raw
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        offers = []
        seen_urls: set[str] = set()

        # Search all text blocks for position-related content
        blocks = []
        for tag in soup.find_all(string=_POSITION_RE):
            parent = tag.find_parent(["div", "section", "article", "li", "p"])
            if parent and parent not in blocks:
                blocks.append(parent)

        if not blocks:
            logger.warning(
                "[rwth_comsys] No position blocks found at %s — no vacancies or structure changed.",
                page_url,
            )
            return []

        for block in blocks:
            link = block.find("a", href=True)
            url = urljoin(_BASE_URL, link["href"]) if link else page_url
            if url in seen_urls:
                continue
            seen_urls.add(url)

            heading = block.find(["h1", "h2", "h3", "h4", "strong"])
            title_text = heading.get_text(strip=True) if heading else ""
            if not title_text:
                title_text = block.get_text(strip=True)[:120]
            if not title_text:
                continue

            description = block.get_text(separator=" ", strip=True)[:500]
            offers.append(Offer(
                source=self.source_name,
                title=title_text.strip(),
                institution="RWTH Aachen",
                lab="COMSYS (Wehrle)",
                url=url.strip(),
                country="DE",
                location="Aachen",
                funding_type="TV-L E13",
                description=description,
            ))

        return offers
