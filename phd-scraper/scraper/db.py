"""
SQLite storage layer: table creation, insertion with deduplication, and queries.
"""
from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from scraper.models import Offer

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS offers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,
    title         TEXT NOT NULL,
    institution   TEXT,
    lab           TEXT,
    professor     TEXT,
    url           TEXT NOT NULL,
    url_hash      TEXT NOT NULL UNIQUE,
    country       TEXT,
    location      TEXT,
    funding_type  TEXT,
    language      TEXT,
    deadline      TEXT,
    published_at  TEXT,
    keywords_hit  TEXT,
    first_seen_at TEXT NOT NULL,
    notified_at   TEXT,
    status        TEXT DEFAULT 'new'
);

CREATE INDEX IF NOT EXISTS idx_offers_url_hash ON offers(url_hash);
CREATE INDEX IF NOT EXISTS idx_offers_status   ON offers(status);

CREATE TABLE IF NOT EXISTS users (
    chat_id     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'user',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invite_tokens (
    token       TEXT PRIMARY KEY,
    created_by  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    used_by     TEXT,
    used_at     TEXT,
    status      TEXT DEFAULT 'active'
);
"""




def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Return a sqlite3 connection with row_factory set to Row."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | Path) -> None:
    """Create the database schema if it does not already exist."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with get_connection(db_path) as conn:
        conn.executescript(_DDL)
    logger.info("Database initialised at %s", db_path)


def insert_offer(conn: sqlite3.Connection, offer: Offer) -> bool:
    """
    Insert an offer using INSERT OR IGNORE (dedup by url_hash).
    Returns True if the offer was newly inserted, False if it already existed.
    """
    now = datetime.now(timezone.utc).isoformat()
    sql = """
    INSERT OR IGNORE INTO offers
        (source, title, institution, lab, professor, url, url_hash,
         country, location, funding_type, language, deadline,
         published_at, keywords_hit, first_seen_at, status)
    VALUES
        (:source, :title, :institution, :lab, :professor, :url, :url_hash,
         :country, :location, :funding_type, :language, :deadline,
         :published_at, :keywords_hit, :first_seen_at, 'new')
    """
    params = {
        "source": offer.source,
        "title": offer.title,
        "institution": offer.institution,
        "lab": offer.lab,
        "professor": offer.professor,
        "url": offer.url,
        "url_hash": offer.url_hash,
        "country": offer.country,
        "location": offer.location,
        "funding_type": offer.funding_type,
        "language": offer.language,
        "deadline": offer.deadline,
        "published_at": offer.published_at,
        "keywords_hit": offer.keywords_hit,
        "first_seen_at": now,
    }
    cursor = conn.execute(sql, params)
    conn.commit()
    inserted = cursor.rowcount > 0
    if inserted:
        logger.debug("Inserted new offer: %s [%s]", offer.title, offer.source)
    else:
        logger.debug("Duplicate offer skipped: %s", offer.url_hash[:12])
    return inserted


def mark_notified(conn: sqlite3.Connection, offer_ids: list[int]) -> None:
    """Mark offers as notified after a Telegram message was sent."""
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "UPDATE offers SET notified_at = ?, status = 'notified' WHERE id = ?",
        [(now, oid) for oid in offer_ids],
    )
    conn.commit()


def get_new_offers(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all offers with status='new' (not yet notified)."""
    cursor = conn.execute(
        "SELECT * FROM offers WHERE status = 'new' ORDER BY first_seen_at DESC"
    )
    return cursor.fetchall()


def get_all_offers(conn: sqlite3.Connection, status: Optional[str] = None) -> list[sqlite3.Row]:
    """Return all offers, optionally filtered by status."""
    if status:
        cursor = conn.execute(
            "SELECT * FROM offers WHERE status = ? ORDER BY first_seen_at DESC",
            (status,),
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM offers ORDER BY first_seen_at DESC"
        )
    return cursor.fetchall()


def mark_offer_status(conn: sqlite3.Connection, offer_id: int, status: str) -> bool:
    """
    Manually set the status of an offer (e.g. 'applied', 'ignored', 'expired').
    Returns True if a row was updated.
    """
    valid_statuses = {"new", "notified", "applied", "ignored", "expired"}
    if status not in valid_statuses:
        raise ValueError(f"Invalid status '{status}'. Must be one of {valid_statuses}")
    cursor = conn.execute(
        "UPDATE offers SET status = ? WHERE id = ?", (status, offer_id)
    )
    conn.commit()
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# User Administration Layer
# ---------------------------------------------------------------------------

def add_user(conn: sqlite3.Connection, chat_id: int, name: str, role: str = "user") -> bool:
    """Authorize a new user with a chat_id, name, and role ('admin' or 'user')."""
    now = datetime.now(timezone.utc).isoformat()
    sql = """
    INSERT INTO users (chat_id, name, role, created_at)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(chat_id) DO UPDATE SET name=excluded.name, role=excluded.role
    """
    cursor = conn.execute(sql, (chat_id, name, role, now))
    conn.commit()
    return cursor.rowcount > 0


def remove_user(conn: sqlite3.Connection, chat_id: int) -> bool:
    """Revoke authorization for a user by chat_id."""
    cursor = conn.execute("DELETE FROM users WHERE chat_id = ?", (chat_id,))
    conn.commit()
    return cursor.rowcount > 0


def get_all_users(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all authorized users."""
    cursor = conn.execute("SELECT * FROM users ORDER BY created_at ASC")
    return cursor.fetchall()


def is_user_authorized(conn: sqlite3.Connection, chat_id: int | str, super_admin_id: str | int | None = None) -> bool:
    """Check if a chat_id is the primary super admin or stored in users table."""
    cid_str = str(chat_id).strip()
    if super_admin_id and str(super_admin_id).strip() == cid_str:
        return True

    cursor = conn.execute("SELECT 1 FROM users WHERE chat_id = ?", (int(cid_str) if cid_str.isdigit() else cid_str,))
    return cursor.fetchone() is not None


def is_admin(conn: sqlite3.Connection, chat_id: int | str, super_admin_id: str | int | None = None) -> bool:
    """Check if a chat_id has administrative privileges."""
    cid_str = str(chat_id).strip()
    if super_admin_id and str(super_admin_id).strip() == cid_str:
        return True

    cursor = conn.execute(
        "SELECT 1 FROM users WHERE chat_id = ? AND role = 'admin'",
        (int(cid_str) if cid_str.isdigit() else cid_str,)
    )
    return cursor.fetchone() is not None


# ---------------------------------------------------------------------------
# Invite Tokens Layer (Deep Linking)
# ---------------------------------------------------------------------------

import secrets

def create_invite_token(conn: sqlite3.Connection, created_by: int | str) -> str:
    """Generate and store a new single-use invite token."""
    token = secrets.token_hex(4)  # 8 hex characters
    now = datetime.now(timezone.utc).isoformat()
    sql = "INSERT INTO invite_tokens (token, created_by, created_at, status) VALUES (?, ?, ?, 'active')"
    conn.execute(sql, (token, str(created_by), now))
    conn.commit()
    return token


def validate_and_consume_token(conn: sqlite3.Connection, token: str, user_chat_id: int | str, user_name: str) -> bool:
    """Check if token is active, authorize user, and mark token as used."""
    cur = conn.execute("SELECT * FROM invite_tokens WHERE token = ? AND status = 'active'", (token,))
    row = cur.fetchone()
    if not row:
        return False

    now = datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE invite_tokens SET status = 'used', used_by = ?, used_at = ? WHERE token = ?", (str(user_chat_id), now, token))
    add_user(conn, int(user_chat_id) if str(user_chat_id).isdigit() else user_chat_id, user_name, role="user")
    conn.commit()
    return True


