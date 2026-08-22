"""Tests for the SQLite storage layer — especially deduplication."""
from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path

from scraper.models import Offer
from scraper import db


@pytest.fixture
def tmp_db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test_offers.db"
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    yield conn
    conn.close()


def make_offer(url: str = "https://example.com/offer/1", **kwargs) -> Offer:
    defaults = dict(
        source="test",
        title="PhD in Distributed Systems",
        url=url,
    )
    defaults.update(kwargs)
    return Offer(**defaults)


class TestInitDb:
    def test_creates_table(self, tmp_path: Path):
        db_path = tmp_path / "new.db"
        db.init_db(db_path)
        conn = db.get_connection(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='offers'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_idempotent(self, tmp_path: Path):
        db_path = tmp_path / "idem.db"
        db.init_db(db_path)
        db.init_db(db_path)  # should not raise


class TestInsertOffer:
    def test_inserts_successfully(self, tmp_db):
        offer = make_offer()
        inserted = db.insert_offer(tmp_db, offer)
        assert inserted is True
        rows = db.get_all_offers(tmp_db)
        assert len(rows) == 1

    def test_dedup_same_url(self, tmp_db):
        """Same URL inserted twice must result in exactly one row."""
        offer = make_offer(url="https://example.com/offer/99")
        first = db.insert_offer(tmp_db, offer)
        second = db.insert_offer(tmp_db, offer)
        assert first is True
        assert second is False
        rows = db.get_all_offers(tmp_db)
        assert len(rows) == 1

    def test_dedup_url_trailing_slash(self, tmp_db):
        """Trailing slash differences in URL are normalized to the same hash."""
        offer_a = make_offer(url="https://example.com/offer/42")
        offer_b = make_offer(url="https://example.com/offer/42/")
        db.insert_offer(tmp_db, offer_a)
        second = db.insert_offer(tmp_db, offer_b)
        assert second is False

    def test_different_urls_both_inserted(self, tmp_db):
        offer_a = make_offer(url="https://example.com/offer/1")
        offer_b = make_offer(url="https://example.com/offer/2")
        db.insert_offer(tmp_db, offer_a)
        db.insert_offer(tmp_db, offer_b)
        rows = db.get_all_offers(tmp_db)
        assert len(rows) == 2

    def test_default_status_is_new(self, tmp_db):
        db.insert_offer(tmp_db, make_offer())
        rows = db.get_all_offers(tmp_db)
        assert rows[0]["status"] == "new"


class TestGetNewOffers:
    def test_returns_only_new(self, tmp_db):
        offer_a = make_offer(url="https://example.com/1")
        offer_b = make_offer(url="https://example.com/2")
        db.insert_offer(tmp_db, offer_a)
        db.insert_offer(tmp_db, offer_b)
        # Mark one as notified
        all_rows = db.get_all_offers(tmp_db)
        db.mark_notified(tmp_db, [all_rows[0]["id"]])

        new_rows = db.get_new_offers(tmp_db)
        assert len(new_rows) == 1
        assert new_rows[0]["status"] == "new"


class TestMarkOfferStatus:
    def test_mark_applied(self, tmp_db):
        db.insert_offer(tmp_db, make_offer())
        row = db.get_all_offers(tmp_db)[0]
        updated = db.mark_offer_status(tmp_db, row["id"], "applied")
        assert updated is True
        row2 = db.get_all_offers(tmp_db, status="applied")[0]
        assert row2["status"] == "applied"

    def test_invalid_status_raises(self, tmp_db):
        db.insert_offer(tmp_db, make_offer())
        row = db.get_all_offers(tmp_db)[0]
        with pytest.raises(ValueError, match="Invalid status"):
            db.mark_offer_status(tmp_db, row["id"], "nonexistent")

    def test_nonexistent_id_returns_false(self, tmp_db):
        updated = db.mark_offer_status(tmp_db, 9999, "ignored")
        assert updated is False
