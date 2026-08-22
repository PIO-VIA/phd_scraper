"""
CNRS emploi scraper — French national research center job portal.
URL: https://emploi.cnrs.fr/
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup

from scraper.base import BaseScraper
from scraper.models import Offer

logger = logging.getLogger(__name__)

_BASE_URL = "https://emploi.cnrs.fr"
# URL discovered by inspecting the filtered search for "Doctorant" contracts
_SEARCH_URL = _BASE_URL + "/Offres/Doctorant/"


class CnrsScraper(BaseScraper):
    source_name = "cnrs"

    def fetch(self) -> str:
        if not self.check_robots(_BASE_URL, "/Offres/"):
            return ""
        try:
            resp = self.get(_SEARCH_URL)
            return resp.text
        except Exception as exc:
            logger.warning("[cnrs] Failed to fetch listing: %s", exc)
            return ""

    def parse(self, raw: str) -> list[Offer]:
        if not raw:
            return []
        soup = BeautifulSoup(raw, "lxml")
        offers = []

        # CNRS portal typically lists offers in table rows or divs
        cards = soup.select(
            "tr.offre, div.offre, article.job-offer, "
            ".result-item, .job-listing-item"
        )
        if not cards:
            # Fallback: grab all links pointing to /Offres/Doctorant/<ref>/
            links = soup.find_all(
                "a", href=re.compile(r"/Offres/Doctorant/", re.I)
            )
            if not links:
                logger.warning(
                    "[cnrs] No offer links found — structure may have changed."
                )
                return []
            cards = links

        seen_urls: set[str] = set()
        for card in cards:
            link = card if card.name == "a" else card.find("a", href=re.compile(r"/Offres/", re.I))
            if not link:
                continue
            url = urljoin(_BASE_URL, link["href"])
            if url in seen_urls:
                continue
            seen_urls.add(url)

            title_tag = card.find(["h2", "h3", "h4", "td", "span"]) if card.name != "a" else None
            title = (
                title_tag.get_text(strip=True)
                if title_tag
                else link.get_text(strip=True)
            )
            if not title:
                continue

            # Extract UMR/lab code from URL if present
            umr_match = re.search(r"/Offres/Doctorant/([^/]+)/", url)
            lab = umr_match.group(1) if umr_match else None

            offers.append(Offer(
                source=self.source_name,
                title=title.strip(),
                lab=lab,
                url=url.strip(),
                country="FR",
                funding_type="Contrat doctoral",
            ))
        return offers
