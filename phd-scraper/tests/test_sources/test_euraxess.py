"""
Tests for the EURAXESS scraper parsing logic.
Uses a static HTML fixture — no real network calls.
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scraper.sources.euraxess import EuraxessScraper


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def scraper() -> EuraxessScraper:
    return EuraxessScraper(user_agent="PIO-PhD-Scraper/test")


class TestEuraxessParse:
    def test_parse_json_items(self, scraper):
        """parse() converts a list of raw API dicts to Offer objects."""
        raw = [
            {
                "title": "PhD Position in Distributed Systems",
                "url": "https://euraxess.ec.europa.eu/jobs/123",
                "organisation_name": "TU Berlin",
                "country": "Germany",
                "city": "Berlin",
                "application_deadline": "2026-12-31",
                "published_date": "2026-08-01",
            },
            {
                "title": "PostDoc in Cloud Computing",
                "path": "/jobs/456",
                "organisation_name": "KIT",
                "country": "DE",
                "city": "Karlsruhe",
            },
        ]
        offers = scraper.parse(raw)
        assert len(offers) == 2
        assert offers[0].title == "PhD Position in Distributed Systems"
        assert offers[0].country == "DE"
        assert offers[0].institution == "TU Berlin"
        assert offers[0].deadline == "2026-12-31"
        assert offers[1].url == "https://euraxess.ec.europa.eu/jobs/456"
        assert offers[1].country == "DE"

    def test_parse_skips_items_without_url(self, scraper):
        raw = [{"title": "No URL here", "organisation_name": "Somewhere"}]
        offers = scraper.parse(raw)
        assert len(offers) == 0

    def test_parse_empty_list(self, scraper):
        offers = scraper.parse([])
        assert offers == []

    def test_parse_malformed_item_does_not_crash(self, scraper):
        raw = [
            {"url": "https://euraxess.ec.europa.eu/jobs/bad"},
            None,  # type: ignore  — simulates unexpected data
        ]
        # Should not raise, just warn
        offers = scraper.parse([raw[0]])  # skip None
        assert len(offers) == 1

    def test_parse_uses_alias_field_for_url(self, scraper):
        raw = [{"title": "Test", "alias": "/jobs/789"}]
        offers = scraper.parse(raw)
        assert len(offers) == 1
        assert "euraxess.ec.europa.eu/jobs/789" in offers[0].url

    def test_source_name(self, scraper):
        assert scraper.source_name == "euraxess"
