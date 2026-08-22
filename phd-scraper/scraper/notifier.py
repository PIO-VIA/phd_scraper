"""
Telegram notification module.
Sends new PhD offer alerts via the Telegram Bot API.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from typing import Sequence

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
# Max characters for a single Telegram message (hard limit: 4096)
MAX_MSG_LEN = 4000
# If more than this many new offers found in one run, send a summary batch
BATCH_THRESHOLD = 5


def _build_offer_text(row: sqlite3.Row) -> str:
    """Format a single offer row into a human-readable Telegram message block."""
    country = row["country"] or "?"
    source = row["source"] or "?"
    title = row["title"] or "(sans titre)"
    institution = row["institution"] or "?"
    lab = row["lab"] or ""
    professor = row["professor"] or ""
    funding = row["funding_type"] or "non précisé"
    deadline = row["deadline"] or "non précisée"
    url = row["url"] or ""
    keywords = row["keywords_hit"] or ""

    parts = [f"🎓 *Nouvelle offre [{source} — {country}]*"]
    parts.append(f"*{title}*")

    meta = " — ".join(filter(None, [institution, lab, professor]))
    if meta:
        parts.append(meta)

    parts.append(f"💰 Financement : {funding}")
    parts.append(f"📅 Deadline : {deadline}")
    if keywords:
        parts.append(f"🔑 Mots-clés : {keywords}")
    parts.append(f"🔗 {url}")

    return "\n".join(parts)


def send_notifications(
    new_offer_rows: Sequence[sqlite3.Row],
    token: str | None = None,
    chat_id: str | None = None,
) -> list[int]:
    """
    Send Telegram notifications for new offers.
    Returns the list of offer IDs that were successfully notified.

    If ≤ BATCH_THRESHOLD offers, sends one message per offer.
    If > BATCH_THRESHOLD, sends a single summary message with all offers.
    """
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.warning(
            "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping notifications."
        )
        return []

    if not new_offer_rows:
        logger.info("No new offers to notify.")
        return []

    notified_ids: list[int] = []
    url = TELEGRAM_API.format(token=token)

    if len(new_offer_rows) <= BATCH_THRESHOLD:
        # One message per offer
        for row in new_offer_rows:
            text = _build_offer_text(row)
            if _post_message(url, chat_id, text):
                notified_ids.append(row["id"])
    else:
        # One summary message
        header = (
            f"📬 *{len(new_offer_rows)} nouvelles offres PhD trouvées !*\n"
            "Voici le récapitulatif :\n\n"
        )
        blocks = [_build_offer_text(row) for row in new_offer_rows]
        separator = "\n\n" + "─" * 30 + "\n\n"
        full_text = header + separator.join(blocks)

        # Truncate if needed (rare but safe)
        if len(full_text) > MAX_MSG_LEN:
            full_text = full_text[:MAX_MSG_LEN] + "\n…(tronqué)"

        if _post_message(url, chat_id, full_text):
            notified_ids = [row["id"] for row in new_offer_rows]

    logger.info(
        "Notifications sent for %d/%d offers.", len(notified_ids), len(new_offer_rows)
    )
    return notified_ids


def _post_message(api_url: str, chat_id: str, text: str) -> bool:
    """POST a single message to the Telegram sendMessage endpoint."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }
    try:
        resp = httpx.post(api_url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.debug("Telegram message sent (chat_id=%s)", chat_id)
        return True
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Telegram API error %s: %s", exc.response.status_code, exc.response.text
        )
    except httpx.RequestError as exc:
        logger.error("Network error sending Telegram message: %s", exc)
    return False


def send_test_message(
    token: str | None = None,
    chat_id: str | None = None,
) -> bool:
    """Send a simple test ping to verify bot configuration."""
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
    url = TELEGRAM_API.format(token=token)
    return _post_message(
        url,
        chat_id,
        "✅ *PhD Scraper* — bot Telegram opérationnel !",
    )
