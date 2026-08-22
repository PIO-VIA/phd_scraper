"""
Tests for TUM DSE lab scraper.
"""
from __future__ import annotations

from pathlib import Path
import pytest

from scraper.sources.lab_tum_dse import TumDseScraper

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "tum_dse.html"


@pytest.fixture
def scraper() -> TumDseScraper:
    return TumDseScraper(user_agent="PIO-PhD-Scraper/test")


class TestTumDseParse:
    def test_parse_html(self, scraper):
        html = FIXTURE_PATH.read_text(encoding="utf-8")
        offers = scraper.parse(html)
        assert len(offers) == 1
        assert offers[0].country == "DE"
        assert offers[0].institution == "TU Munich"
        assert "DSE Systems Research Group" in offers[0].lab
        assert offers[0].url == "https://dse.in.tum.de/jobs/phd-cloud"

    def test_source_name(self, scraper):
        assert scraper.source_name == "lab_tum_dse"
