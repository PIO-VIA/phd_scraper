"""
Tests for Inria scraper parsing.
"""
from __future__ import annotations

from pathlib import Path
import pytest

from scraper.sources.inria import InriaScraper

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "inria.html"


@pytest.fixture
def scraper() -> InriaScraper:
    return InriaScraper(user_agent="PIO-PhD-Scraper/test")


class TestInriaParse:
    def test_parse_html(self, scraper):
        html = FIXTURE_PATH.read_text(encoding="utf-8")
        offers = scraper.parse(html)
        assert len(offers) == 2
        assert offers[0].country == "FR"
        assert "Cloud Native" in offers[0].title
        assert offers[0].location == "Grenoble"
        assert offers[0].lab == "Équipe SPDR"
        assert offers[1].location == "Rennes"
        assert offers[1].lab == "Équipe MYRIADS"

    def test_parse_rss(self, scraper):
        rss_xml = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0">
          <channel>
            <title>Inria Offres</title>
            <item>
              <title>Thèse en Cloud Computing</title>
              <link>https://jobs.inria.fr/public/classic/fr/offres/2026-999</link>
              <summary>Localisation : Paris</summary>
              <pubDate>Thu, 20 Aug 2026 10:00:00 GMT</pubDate>
            </item>
          </channel>
        </rss>"""
        offers = scraper.parse(rss_xml)
        assert len(offers) == 1
        assert offers[0].title == "Thèse en Cloud Computing"
        assert offers[0].url == "https://jobs.inria.fr/public/classic/fr/offres/2026-999"
        assert offers[0].country == "FR"
        assert offers[0].location == "Paris"

    def test_source_name(self, scraper):
        assert scraper.source_name == "inria"
