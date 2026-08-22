"""
Abstract base class for all PhD offer scrapers.
"""
from __future__ import annotations

import logging
import time
import urllib.robotparser
from abc import ABC, abstractmethod
from typing import Any

import httpx

from scraper.models import Offer

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 12      # seconds
MAX_RETRIES = 2
INTER_REQUEST_DELAY = 1.5  # seconds between requests to the same domain


class BaseScraper(ABC):
    """
    Abstract base class every scraper must inherit from.

    Subclasses must implement:
      - source_name: str   (class attribute)
      - fetch()            → raw content (str HTML, dict JSON, or feedparser result)
      - parse(raw)         → list[Offer]
    """

    source_name: str = "unknown"

    def __init__(self, user_agent: str | None = None) -> None:
        import os
        self.user_agent = user_agent or os.environ.get(
            "USER_AGENT", "PIO-PhD-Scraper/1.0 (contact: your-email@example.com)"
        )
        self._client = httpx.Client(
            headers={"User-Agent": self.user_agent},
            timeout=DEFAULT_TIMEOUT,
            follow_redirects=True,
        )

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def fetch(self) -> Any:
        """Retrieve raw content from the source (HTML string, dict, or parsed feed)."""

    @abstractmethod
    def parse(self, raw: Any) -> list[Offer]:
        """Transform raw content into a normalized list of Offer objects."""

    # ------------------------------------------------------------------
    # Orchestration (concrete)
    # ------------------------------------------------------------------

    def run(self) -> list[Offer]:
        """
        Execute fetch() → parse() with error handling.
        Never raises — returns an empty list on failure.
        """
        try:
            raw = self.fetch()
        except Exception as exc:
            logger.error("[%s] fetch() failed: %s", self.source_name, exc)
            return []

        try:
            offers = self.parse(raw)
        except Exception as exc:
            logger.error("[%s] parse() failed: %s", self.source_name, exc)
            return []

        logger.info("[%s] %d offer(s) retrieved.", self.source_name, len(offers))
        return offers

    # ------------------------------------------------------------------
    # Helpers for subclasses
    # ------------------------------------------------------------------

    def get(self, url: str, **kwargs) -> httpx.Response:
        """
        HTTP GET with retry logic and inter-request delay.
        Raises httpx.HTTPError on final failure.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self._client.get(url, **kwargs)
                resp.raise_for_status()
                return resp
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                if attempt == MAX_RETRIES:
                    raise
                logger.warning(
                    "[%s] Request attempt %d/%d failed (%s). Retrying…",
                    self.source_name, attempt, MAX_RETRIES, exc,
                )
                time.sleep(INTER_REQUEST_DELAY)
        # Unreachable, satisfies type checkers
        raise RuntimeError("Exceeded max retries")

    def check_robots(self, base_url: str, path: str) -> bool:
        """
        Check robots.txt compliance for the given URL path.
        Returns True if scraping is allowed (or robots.txt unreachable).
        Logs a WARNING if disallowed.
        """
        rp = urllib.robotparser.RobotFileParser()
        robots_url = base_url.rstrip("/") + "/robots.txt"
        try:
            rp.set_url(robots_url)
            rp.read()
            allowed = rp.can_fetch(self.user_agent, base_url.rstrip("/") + path)
            if not allowed:
                logger.warning(
                    "[%s] robots.txt disallows scraping '%s'. Skipping.",
                    self.source_name, path,
                )
            return allowed
        except Exception as exc:
            logger.debug(
                "[%s] Could not read robots.txt (%s) — proceeding.", self.source_name, exc
            )
            return True  # Assume allowed if unreachable

    def sleep(self, seconds: float = INTER_REQUEST_DELAY) -> None:
        """Polite delay between sequential requests."""
        time.sleep(seconds)

    def __del__(self):
        try:
            self._client.close()
        except Exception:
            pass
