"""
TUM DSE (Systems Research Group, Bhatotia) lab scraper.
URL: https://dse.in.tum.de/
Open positions are announced on the lab homepage — no dedicated positions page.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.base import BaseScraper
from scraper.models import Offer

logger = logging.getLogger(__name__)

_BASE_URL = "https://dse.in.tum.de"
_HOME_URL = _BASE_URL + "/"
_OPENINGS_KEYWORDS = re.compile(
    r"\b(opening|open position|phd|postdoc|doctorate|job|vacancy|hiring)\b",
    re.I,
)


class TumDseScraper(BaseScraper):
    source_name = "lab_tum_dse"

    def fetch(self) -> str:
        if not self.check_robots(_BASE_URL, "/"):
            return ""
        try:
            resp = self.get(_HOME_URL)
            return resp.text
        except Exception as exc:
            logger.warning("[tum_dse] Failed to fetch homepage: %s", exc)
            return ""

    def parse(self, raw: str) -> list[Offer]:
        if not raw:
            return []
        soup = BeautifulSoup(raw, "lxml")
        offers = []

        # Look for sections mentioning openings
        relevant_blocks = []
        for tag in soup.find_all(string=_OPENINGS_KEYWORDS):
            parent = tag.find_parent(["div", "section", "article", "li", "p"])
            if parent and parent not in relevant_blocks:
                relevant_blocks.append(parent)

        if not relevant_blocks:
            logger.warning(
                "[tum_dse] No opening blocks found on homepage — no positions or structure changed."
            )
            return []

        seen_urls: set[str] = set()
        for block in relevant_blocks:
            # Try to find a hyperlink in or near the block
            link = block.find("a", href=True)
            url = urljoin(_BASE_URL, link["href"]) if link else _HOME_URL
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Use heading or text as title
            heading = block.find(["h1", "h2", "h3", "h4", "strong"])
            title = (
                heading.get_text(strip=True)
                if heading
                else block.get_text(strip=True)[:120]
            )
            if not title:
                continue

            description = block.get_text(separator=" ", strip=True)[:500]
            offers.append(Offer(
                source=self.source_name,
                title=title.strip(),
                institution="TU Munich",
                lab="DSE Systems Research Group (Bhatotia)",
                url=url.strip(),
                country="DE",
                location="Munich",
                funding_type="TV-L E13",
                description=description,
            ))

        return offers
