"""
Tests for CNRS scraper.
"""
from __future__ import annotations

from pathlib import Path
import pytest

from scraper.sources.cnrs import CnrsScraper

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "cnrs.html"


@pytest.fixture
def scraper() -> CnrsScraper:
    return CnrsScraper(user_agent="PIO-PhD-Scraper/test")


class TestCnrsParse:
    def test_parse_html(self, scraper):
        html = FIXTURE_PATH.read_text(encoding="utf-8")
        offers = scraper.parse(html)
        assert len(offers) == 2
        assert offers[0].country == "FR"
        assert "Systèmes Cloud" in offers[0].title
        assert offers[0].lab == "UMR5157-ALELAC-001"
        assert offers[0].funding_type == "Contrat doctoral"
        assert offers[1].lab == "UMR7000-JANDOE-002"

    def test_source_name(self, scraper):
        assert scraper.source_name == "cnrs"
