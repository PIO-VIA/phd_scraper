"""
Telegram notification module.
Sends new PhD offer alerts via Telegram with interactive inline action buttons.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from typing import Sequence, Any

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
MAX_MSG_LEN = 4000
BATCH_THRESHOLD = 5


def register_bot_commands(token: str | None = None) -> bool:
    """
    Register official bot commands with Telegram API so they appear in the command menu.
    """
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return False

    url = TELEGRAM_API.format(token=token, method="setMyCommands")
    commands = [
        {"command": "start", "description": "🚀 Démarrer et afficher le menu principal"},
        {"command": "scan", "description": "🔍 Lancer un scan des opportunités"},
        {"command": "latest", "description": "📋 Voir les dernières offres doctorales"},
        {"command": "stats", "description": "📊 Voir les statistiques des offres"},
        {"command": "help", "description": "❓ Aide et liste des commandes"},
    ]
    try:
        resp = httpx.post(url, json={"commands": commands}, timeout=10)
        resp.raise_for_status()
        logger.info("Registered Telegram bot commands successfully.")
        return True
    except Exception as exc:
        logger.warning("Failed to register Telegram bot commands: %s", exc)
        return False


def get_main_reply_keyboard() -> dict[str, Any]:
    """Return persistent reply keyboard with visual action buttons."""
    return {
        "keyboard": [
            [{"text": "🔍 Scanner"}, {"text": "📋 Offres (5)"}],
            [{"text": "📊 Stats"}, {"text": "❓ Aide"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def get_offer_inline_keyboard(offer_id: int, offer_url: str | None = None) -> dict[str, Any]:
    """Return inline keyboard buttons for an offer notification."""
    buttons = [
        [
            {"text": "✅ Postulé", "callback_data": f"apply_{offer_id}"},
            {"text": "🙈 Ignorer", "callback_data": f"ignore_{offer_id}"},
        ]
    ]
    if offer_url:
        buttons.append([{"text": "🔗 Voir l'offre", "url": offer_url}])

    return {"inline_keyboard": buttons}


def _build_offer_text(row: sqlite3.Row) -> str:
    """Format a single offer row into a Telegram Markdown text block."""
    offer_id = row["id"]
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
    status = row["status"] or "new"

    status_icon = "🆕" if status == "new" else ("✅" if status == "applied" else "🙈")

    parts = [f"🎓 *Offre #{offer_id} [{source} — {country}]* {status_icon}"]
    parts.append(f"*{title}*")

    meta = " — ".join(filter(None, [institution, lab, professor]))
    if meta:
        parts.append(f"🏛️ {meta}")

    parts.append(f"💰 Financement : {funding}")
    parts.append(f"📅 Deadline : {deadline}")
    if keywords:
        parts.append(f"🔑 Mots-clés : `{keywords}`")
    if url:
        parts.append(f"🔗 [Lien vers l'offre]({url})")

    return "\n".join(parts)


def send_notifications(
    new_offer_rows: Sequence[sqlite3.Row],
    token: str | None = None,
    chat_id: str | None = None,
) -> list[int]:
    """
    Send Telegram notifications for new offers.
    Returns the list of offer IDs that were successfully notified.
    """
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping notifications.")
        return []

    if not new_offer_rows:
        logger.info("No new offers to notify.")
        return []

    # Register commands dynamically
    register_bot_commands(token)

    notified_ids: list[int] = []

    if len(new_offer_rows) <= BATCH_THRESHOLD:
        for row in new_offer_rows:
            text = _build_offer_text(row)
            kb = get_offer_inline_keyboard(row["id"], row["url"])
            if send_message(text, token=token, chat_id=chat_id, reply_markup=kb):
                notified_ids.append(row["id"])
    else:
        header = (
            f"📬 *{len(new_offer_rows)} nouvelles offres PhD trouvées !*\n"
            "Voici le récapitulatif :\n\n"
        )
        blocks = [_build_offer_text(row) for row in new_offer_rows]
        separator = "\n\n" + "─" * 30 + "\n\n"
        full_text = header + separator.join(blocks)

        if len(full_text) > MAX_MSG_LEN:
            full_text = full_text[:MAX_MSG_LEN] + "\n…(tronqué)"

        if send_message(full_text, token=token, chat_id=chat_id):
            notified_ids = [row["id"] for row in new_offer_rows]

    logger.info("Notifications sent for %d/%d offers.", len(notified_ids), len(new_offer_rows))
    return notified_ids


def send_message(
    text: str,
    token: str | None = None,
    chat_id: str | None = None,
    reply_markup: dict[str, Any] | None = None,
) -> bool:
    """Send a Telegram message with optional reply_markup (inline or custom keyboard)."""
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False

    url = TELEGRAM_API.format(token=token, method="sendMessage")
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        resp = httpx.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except httpx.HTTPStatusError as exc:
        logger.error("Telegram API error %s: %s", exc.response.status_code, exc.response.text)
    except httpx.RequestError as exc:
        logger.error("Network error sending Telegram message: %s", exc)
    return False


def send_test_message(
    token: str | None = None,
    chat_id: str | None = None,
) -> bool:
    """Send a test ping and register commands."""
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
    register_bot_commands(token)
    
    text = (
        "🤖 *PhD Scraper — Bot Telegram actif !*\n\n"
        "Boutons d'action rapide enregistrés.\n"
        "Tapez /help ou cliquez sur les boutons ci-dessous pour contrôler le scraper."
    )
    return send_message(text, token=token, chat_id=chat_id, reply_markup=get_main_reply_keyboard())
