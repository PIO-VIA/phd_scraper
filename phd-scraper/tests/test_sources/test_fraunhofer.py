"""
Tests for Fraunhofer scraper.
"""
from __future__ import annotations

from pathlib import Path
import pytest

from scraper.sources.fraunhofer import FraunhoferScraper

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "fraunhofer.html"


@pytest.fixture
def scraper() -> FraunhoferScraper:
    return FraunhoferScraper(user_agent="PIO-PhD-Scraper/test")


class TestFraunhoferParse:
    def test_parse_html(self, scraper):
        html = FIXTURE_PATH.read_text(encoding="utf-8")
        offers = scraper.parse([html])
        assert len(offers) == 2
        assert offers[0].country == "DE"
        assert "Cloud Security" in offers[0].title
        assert offers[0].institution == "Fraunhofer ISST"
        assert offers[0].location == "Dortmund"
        assert offers[1].institution == "Fraunhofer FOKUS"
        assert offers[1].location == "Berlin"

    def test_source_name(self, scraper):
        assert scraper.source_name == "fraunhofer"
