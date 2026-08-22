"""
Tests for Max Planck Society scraper.
"""
from __future__ import annotations

from pathlib import Path
import pytest

from scraper.sources.max_planck import MaxPlanckScraper

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "max_planck.html"


@pytest.fixture
def scraper() -> MaxPlanckScraper:
    return MaxPlanckScraper(user_agent="PIO-PhD-Scraper/test")


class TestMaxPlanckParse:
    def test_parse_html(self, scraper):
        html = FIXTURE_PATH.read_text(encoding="utf-8")
        offers = scraper.parse(html)
        assert len(offers) == 2
        assert offers[0].country == "DE"
        assert "Distributed Systems" in offers[0].title
        assert offers[0].institution == "MPI-SWS (Software Systems)"
        assert offers[0].deadline == "2026-11-30"
        assert offers[1].institution == "MPI for Informatics"
        assert offers[1].deadline == "2026-12-15"

    def test_source_name(self, scraper):
        assert scraper.source_name == "max_planck"
