"""
Tests for CampusFrance scraper.
"""
from __future__ import annotations

from pathlib import Path
import pytest

from scraper.sources.campusfrance import CampusFranceScraper

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "campusfrance.html"


@pytest.fixture
def scraper() -> CampusFranceScraper:
    return CampusFranceScraper(user_agent="PIO-PhD-Scraper/test")


class TestCampusFranceParse:
    def test_parse_html(self, scraper):
        html = FIXTURE_PATH.read_text(encoding="utf-8")
        offers = scraper.parse(html)
        assert len(offers) == 2
        assert offers[0].country == "FR"
        assert "Observability" in offers[0].title
        assert offers[0].funding_type == "Contrat doctoral"
        assert "Consensus Protocols" in offers[1].title

    def test_source_name(self, scraper):
        assert scraper.source_name == "campusfrance"
