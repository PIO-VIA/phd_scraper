"""
Tests for RWTH COMSYS scraper.
"""
from __future__ import annotations

from pathlib import Path
import pytest

from scraper.sources.lab_rwth_comsys import RwthComSysScraper

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "rwth_comsys.html"


@pytest.fixture
def scraper() -> RwthComSysScraper:
    return RwthComSysScraper(user_agent="PIO-PhD-Scraper/test")


class TestRwthComSysParse:
    def test_parse_html(self, scraper):
        html = FIXTURE_PATH.read_text(encoding="utf-8")
        offers = scraper.parse((html, "https://www.comsys.rwth-aachen.de/jobs/"))
        assert len(offers) == 1
        assert offers[0].country == "DE"
        assert offers[0].institution == "RWTH Aachen"
        assert offers[0].lab == "COMSYS (Wehrle)"
        assert offers[0].url == "https://www.comsys.rwth-aachen.de/jobs/phd-2026/"

    def test_source_name(self, scraper):
        assert scraper.source_name == "lab_rwth_comsys"
