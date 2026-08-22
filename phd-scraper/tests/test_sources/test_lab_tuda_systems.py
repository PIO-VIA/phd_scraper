"""
Tests for TU Darmstadt Systems scraper.
"""
from __future__ import annotations

from pathlib import Path
import pytest

from scraper.sources.lab_tuda_systems import TudaSystemsScraper

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "tuda_systems.html"


@pytest.fixture
def scraper() -> TudaSystemsScraper:
    return TudaSystemsScraper(user_agent="PIO-PhD-Scraper/test")


class TestTudaSystemsParse:
    def test_parse_html(self, scraper):
        html = FIXTURE_PATH.read_text(encoding="utf-8")
        offers = scraper.parse(html)
        assert len(offers) == 1
        assert offers[0].country == "DE"
        assert offers[0].institution == "TU Darmstadt"
        assert offers[0].published_at == "2026-08-10"
        assert "Accelerator Systems" in offers[0].title

    def test_source_name(self, scraper):
        assert scraper.source_name == "lab_tuda_systems"
