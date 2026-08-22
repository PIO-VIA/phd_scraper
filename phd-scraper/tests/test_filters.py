"""Tests for the keyword filter logic."""
from __future__ import annotations

import pytest
from scraper.models import Offer
from scraper.filters import matches, filter_offers


KEYWORDS = {
    "include": [
        "cloud computing",
        "distributed systems",
        "kubernetes",
        "edge computing",
    ],
    "exclude": [
        "clinical",
        "biomedical",
    ],
}


def make_offer(**kwargs) -> Offer:
    defaults = dict(source="test", title="Test Offer", url="https://example.com/1")
    defaults.update(kwargs)
    return Offer(**defaults)


class TestMatchesFunction:
    def test_include_keyword_in_title(self):
        offer = make_offer(title="PhD position in Distributed Systems")
        is_match, hits = matches(offer, KEYWORDS)
        assert is_match is True
        assert "distributed systems" in hits

    def test_include_keyword_case_insensitive(self):
        offer = make_offer(title="PhD in CLOUD COMPUTING infrastructure")
        is_match, hits = matches(offer, KEYWORDS)
        assert is_match is True
        assert "cloud computing" in hits

    def test_exclude_keyword_blocks_match(self):
        offer = make_offer(
            title="PhD in Cloud Computing for Biomedical Applications"
        )
        is_match, hits = matches(offer, KEYWORDS)
        assert is_match is False
        assert hits == []

    def test_no_include_hit(self):
        offer = make_offer(title="History of Medieval Art")
        is_match, hits = matches(offer, KEYWORDS)
        assert is_match is False

    def test_include_in_description(self):
        offer = make_offer(
            title="Open PhD Position",
            description="We work on edge computing and IoT systems.",
        )
        is_match, hits = matches(offer, KEYWORDS)
        assert is_match is True
        assert "edge computing" in hits

    def test_include_in_lab(self):
        offer = make_offer(
            title="Open Position",
            lab="Kubernetes Infrastructure Lab",
        )
        is_match, hits = matches(offer, KEYWORDS)
        assert is_match is True
        assert "kubernetes" in hits

    def test_multiple_hits_all_stored(self):
        offer = make_offer(
            title="PhD in Distributed Systems and Cloud Computing"
        )
        is_match, hits = matches(offer, KEYWORDS)
        assert is_match is True
        assert "distributed systems" in hits
        assert "cloud computing" in hits

    def test_empty_include_keywords_returns_all(self):
        """When no include keywords configured, all offers pass through."""
        offer = make_offer(title="Anything goes")
        empty_kw = {"include": [], "exclude": []}
        # filter_offers warns and returns all
        results = filter_offers([offer], keywords=empty_kw)
        assert len(results) == 1


class TestFilterOffers:
    def test_filter_sets_keywords_hit(self):
        offer = make_offer(title="PhD in Distributed Systems")
        results = filter_offers([offer], keywords=KEYWORDS)
        assert len(results) == 1
        assert "distributed systems" in results[0].keywords_hit

    def test_filter_excludes_non_matching(self):
        offers = [
            make_offer(title="PhD in Distributed Systems", url="https://example.com/1"),
            make_offer(title="History of Art", url="https://example.com/2"),
        ]
        results = filter_offers(offers, keywords=KEYWORDS)
        assert len(results) == 1
        assert results[0].title == "PhD in Distributed Systems"

    def test_filter_excludes_blocked(self):
        offers = [
            make_offer(title="Cloud Computing for Clinical Trials", url="https://example.com/3"),
        ]
        results = filter_offers(offers, keywords=KEYWORDS)
        assert len(results) == 0

    def test_filter_empty_list(self):
        assert filter_offers([], keywords=KEYWORDS) == []
