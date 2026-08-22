"""
Tests for ADUM scraper.
"""
from __future__ import annotations

from pathlib import Path
import pytest

from scraper.sources.adum import AdumScraper

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "adum.html"


@pytest.fixture
def scraper() -> AdumScraper:
    return AdumScraper(user_agent="PIO-PhD-Scraper/test")


class TestAdumParse:
    def test_parse_html(self, scraper):
        html = FIXTURE_PATH.read_text(encoding="utf-8")
        offers = scraper.parse(html)
        assert len(offers) == 2
        assert offers[0].country == "FR"
        assert "Cloud Native" in offers[0].title
        assert offers[0].institution == "Université Grenoble Alpes"
        assert offers[0].professor == "Prof. Jean Dupont"
        assert offers[1].institution == "Sorbonne Université"
        assert offers[1].professor == "Prof. Alice Martin"

    def test_source_name(self, scraper):
        assert scraper.source_name == "adum"
