"""
Interactive Telegram Bot listener for PhD Scraper.
Supports long polling, slash commands, custom reply buttons, and inline action callbacks.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from typing import Any

import httpx

from scraper import db, notifier, filters
from scraper.models import Offer

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def answer_callback_query(token: str, callback_id: str, text: str) -> None:
    """Acknowledge a Telegram inline button click with a toast notification."""
    url = TELEGRAM_API.format(token=token, method="answerCallbackQuery")
    try:
        httpx.post(url, json={"callback_query_id": callback_id, "text": text}, timeout=5)
    except Exception as exc:
        logger.warning("Error answering callback query: %s", exc)


def edit_message_text(token: str, chat_id: str | int, message_id: int, text: str, reply_markup: dict[str, Any] | None = None) -> None:
    """Edit an existing Telegram message after an action is performed."""
    url = TELEGRAM_API.format(token=token, method="editMessageText")
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    try:
        httpx.post(url, json=payload, timeout=5)
    except Exception as exc:
        logger.warning("Error editing message text: %s", exc)


def handle_stats_command(token: str, chat_id: str | int, db_path: str) -> None:
    """Compute DB metrics and format a summary dashboard report."""
    conn = db.get_connection(db_path)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM offers")
    total = cur.fetchone()[0]

    cur.execute("SELECT status, COUNT(*) FROM offers GROUP BY status")
    status_counts = dict(cur.fetchall())

    cur.execute("SELECT country, COUNT(*) FROM offers GROUP BY country")
    country_counts = dict(cur.fetchall())
    conn.close()

    new_cnt = status_counts.get("new", 0) + status_counts.get("notified", 0)
    applied_cnt = status_counts.get("applied", 0)
    ignored_cnt = status_counts.get("ignored", 0)

    text = (
        "📊 *Statistiques du PhD Scraper*\n\n"
        f"🌐 Total des offres suivies : *{total}*\n"
        f"🆕 Offres récentes / non traitées : *{new_cnt}*\n"
        f"✅ Offres postulées : *{applied_cnt}*\n"
        f"🙈 Offres ignorées : *{ignored_cnt}*\n\n"
        "📍 *Répartition par pays :*\n"
    )
    for ctry, cnt in country_counts.items():
        flag = "🇩🇪" if ctry == "DE" else ("🇫🇷" if ctry == "FR" else "🇪🇺")
        text += f"• {flag} {ctry} : {cnt} offre(s)\n"

    notifier.send_message(text, token=token, chat_id=str(chat_id), reply_markup=notifier.get_main_reply_keyboard())


def handle_latest_command(token: str, chat_id: str | int, db_path: str, limit: int = 5) -> None:
    """Send the last N stored offers with interactive action buttons."""
    conn = db.get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM offers ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        notifier.send_message("ℹ️ Aucune offre enregistrée dans la base.", token=token, chat_id=str(chat_id))
        return

    notifier.send_message(f"📋 *Voici les {len(rows)} dernières offres enregistrées :*", token=token, chat_id=str(chat_id))

    for row in rows:
        text = notifier._build_offer_text(row)
        kb = notifier.get_offer_inline_keyboard(row["id"], row["url"])
        notifier.send_message(text, token=token, chat_id=str(chat_id), reply_markup=kb)


def handle_scan_command(token: str, chat_id: str | int, db_path: str, load_scrapers_func: Any) -> None:
    """Execute a scan cycle on command and report results to Telegram."""
    notifier.send_message("⏳ *Lancement du scan en direct sur toutes les sources...*", token=token, chat_id=str(chat_id))

    db.init_db(db_path)
    conn = db.get_connection(db_path)
    scrapers = load_scrapers_func()
    keywords = filters.load_keywords()

    all_offers: list[Offer] = []
    ok_sources = []
    fail_sources = []

    for scraper in scrapers:
        try:
            raw = scraper.run()
            ok_sources.append(scraper.source_name)
            matched = filters.filter_offers(raw, keywords)
            all_offers.extend(matched)
        except Exception as exc:
            logger.error("Scan error on %s: %s", scraper.source_name, exc)
            fail_sources.append(scraper.source_name)

    new_ids = []
    for offer in all_offers:
        if db.insert_offer(conn, offer):
            row = conn.execute("SELECT id FROM offers WHERE url_hash = ?", (offer.url_hash,)).fetchone()
            if row:
                new_ids.append(row["id"])

    if new_ids:
        new_rows = [conn.execute("SELECT * FROM offers WHERE id = ?", (oid,)).fetchone() for oid in new_ids]
        new_rows = [r for r in new_rows if r]
        notifier.send_notifications(new_rows, token=token, chat_id=str(chat_id))
        db.mark_notified(conn, new_ids)

    conn.close()

    summary_text = (
        "✅ *Scan terminé !*\n\n"
        f"• Sources analysées : *{len(ok_sources)}/{len(scrapers)}*\n"
        f"• Nouvelles offres découvertes : *{len(new_ids)}*"
    )
    if fail_sources:
        summary_text += f"\n⚠️ *Sources en erreur :* {', '.join(fail_sources)}"

    notifier.send_message(summary_text, token=token, chat_id=str(chat_id), reply_markup=notifier.get_main_reply_keyboard())


def handle_help_command(token: str, chat_id: str | int) -> None:
    """Display bot command menu and help text."""
    help_text = (
        "🤖 *PhD Scraper — Menu & Commandes*\n\n"
        "Vous pouvez taper une commande ou utiliser les boutons ci-dessous :\n\n"
        "• `/scan` ou 🔍 *Scanner* : Déclencher un scraping immédiat de toutes les sources.\n"
        "• `/latest` ou 📋 *Offres (5)* : Consulter les 5 dernières offres enregistrées.\n"
        "• `/stats` ou 📊 *Stats* : Voir les statistiques et le bilan par pays.\n"
        "• `/help` ou ❓ *Aide* : Afficher ce menu interactif.\n\n"
        "💡 *Astuce :* Cliquez directement sur les boutons `[ ✅ Postulé ]` ou `[ 🙈 Ignorer ]` sous les offres pour mettre à jour votre suivi."
    )
    notifier.send_message(help_text, token=token, chat_id=str(chat_id), reply_markup=notifier.get_main_reply_keyboard())


def process_update(update: dict[str, Any], token: str, db_path: str, load_scrapers_func: Any) -> None:
    """Dispatch incoming Telegram update (Message or Callback Query)."""
    # 1. Handle Inline Button Callbacks
    if "callback_query" in update:
        cb = update["callback_query"]
        cb_id = cb["id"]
        data = cb.get("data", "")
        message = cb.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        message_id = message.get("message_id")
        orig_text = message.get("text", "")

        conn = db.get_connection(db_path)

        if data.startswith("apply_"):
            offer_id = int(data.split("_")[1])
            db.mark_offer_status(conn, offer_id, "applied")
            answer_callback_query(token, cb_id, f"✅ Offre #{offer_id} marquée comme postulée !")
            if message_id and chat_id:
                new_text = orig_text.replace("🆕", "✅").replace("🙈", "✅") + "\n\n📌 *Statut : Postulé ✅*"
                edit_message_text(token, chat_id, message_id, new_text)

        elif data.startswith("ignore_"):
            offer_id = int(data.split("_")[1])
            db.mark_offer_status(conn, offer_id, "ignored")
            answer_callback_query(token, cb_id, f"🙈 Offre #{offer_id} ignorée.")
            if message_id and chat_id:
                new_text = orig_text.replace("🆕", "🙈").replace("✅", "🙈") + "\n\n📌 *Statut : Ignoré 🙈*"
                edit_message_text(token, chat_id, message_id, new_text)

        conn.close()
        return

    # 2. Handle Text Messages & Commands
    msg = update.get("message", {})
    text = msg.get("text", "").strip()
    chat_id = msg.get("chat", {}).get("id")

    if not chat_id or not text:
        return

    # Authorized chat filter check if set
    allowed_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if allowed_chat_id and str(chat_id) != str(allowed_chat_id):
        logger.warning("Ignored message from unauthorized chat_id: %s", chat_id)
        return

    text_lower = text.lower()

    if text_lower in ["/start", "/help", "❓ aide", "aide", "help"]:
        handle_help_command(token, chat_id)
    elif text_lower in ["/scan", "🔍 scanner", "scanner", "scan"]:
        handle_scan_command(token, chat_id, db_path, load_scrapers_func)
    elif text_lower in ["/latest", "/list", "📋 offres (5)", "offres", "latest"]:
        handle_latest_command(token, chat_id, db_path)
    elif text_lower in ["/stats", "📊 stats", "stats", "statistiques"]:
        handle_stats_command(token, chat_id, db_path)
    else:
        handle_help_command(token, chat_id)


def run_bot_polling(token: str | None = None, db_path: str | None = None, load_scrapers_func: Any = None) -> None:
    """Start interactive long-polling loop for Telegram bot."""
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    db_path = db_path or os.environ.get("DB_PATH", "data/offers.db")

    if not token:
        logger.error("Cannot start Telegram bot listener: TELEGRAM_BOT_TOKEN is missing.")
        return

    # Register bot command menu
    notifier.register_bot_commands(token)
    logger.info("🤖 Starting Telegram Bot listener loop (Long Polling)...")

    offset = 0
    url = TELEGRAM_API.format(token=token, method="getUpdates")

    while True:
        try:
            resp = httpx.get(url, params={"offset": offset, "timeout": 20}, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    try:
                        process_update(update, token, db_path, load_scrapers_func)
                    except Exception as exc:
                        logger.error("Error processing update %s: %s", update.get("update_id"), exc)
            else:
                logger.warning("Telegram getUpdates returned status %s", resp.status_code)
                time.sleep(3)
        except httpx.RequestError as exc:
            logger.warning("Network error in bot listener: %s — retrying in 5s...", exc)
            time.sleep(5)
        except Exception as exc:
            logger.error("Unexpected error in bot listener loop: %s", exc)
            time.sleep(3)
