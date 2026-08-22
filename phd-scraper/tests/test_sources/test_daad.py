"""
Tests for DAAD PhDGermany scraper.
"""
from __future__ import annotations

from pathlib import Path
import pytest

from scraper.sources.daad_phdgermany import DaadScraper

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "daad.html"


@pytest.fixture
def scraper() -> DaadScraper:
    return DaadScraper(user_agent="PIO-PhD-Scraper/test")


class TestDaadParse:
    def test_parse_html(self, scraper):
        html = FIXTURE_PATH.read_text(encoding="utf-8")
        offers = scraper.parse(html)
        assert len(offers) == 2
        assert offers[0].country == "DE"
        assert "Edge Computing" in offers[0].title
        assert offers[0].institution == "Technical University of Munich"
        assert offers[0].location == "Munich"
        assert offers[0].funding_type == "Entgeltgruppe 13 TV-L"
        assert offers[0].deadline == "2026-10-31"

    def test_empty_raw(self, scraper):
        assert scraper.parse("") == []

    def test_source_name(self, scraper):
        assert scraper.source_name == "daad_phdgermany"
