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


def handle_help_command(token: str, chat_id: str | int, is_admin_user: bool = False) -> None:
    """Display bot command menu and help text."""
    help_text = (
        "🤖 *PhD Scraper — Menu & Commandes*\n\n"
        "Vous pouvez taper une commande ou utiliser les boutons ci-dessous :\n\n"
        "• `/scan` ou 🔍 *Scanner* : Déclencher un scraping immédiat de toutes les sources.\n"
        "• `/latest` ou 📋 *Offres (5)* : Consulter les 5 dernières offres enregistrées.\n"
        "• `/stats` ou 📊 *Stats* : Voir les statistiques et le bilan par pays.\n"
    )
    if is_admin_user:
        help_text += "• `/users` ou 👥 *Utilisateurs* : Gérer et inviter des membres (Admin).\n"

    help_text += (
        "• `/help` ou ❓ *Aide* : Afficher ce menu interactif.\n\n"
        "💡 *Astuce :* Cliquez directement sur les boutons `[ ✅ Postulé ]` ou `[ 🙈 Ignorer ]` sous les offres pour mettre à jour votre suivi."
    )
    notifier.send_message(help_text, token=token, chat_id=str(chat_id), reply_markup=notifier.get_main_reply_keyboard(is_admin_user=is_admin_user))


def get_bot_username(token: str) -> str:
    """Fetch the bot's Telegram username via getMe API."""
    url = TELEGRAM_API.format(token=token, method="getMe")
    try:
        resp = httpx.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("result", {}).get("username", "")
    except Exception as exc:
        logger.warning("Could not fetch bot username: %s", exc)
    return ""


def handle_users_command(token: str, chat_id: str | int, db_path: str, super_admin_id: str | None) -> None:
    """List all authorized users and display administration options (Admin only)."""
    conn = db.get_connection(db_path)
    if not db.is_admin(conn, chat_id, super_admin_id):
        conn.close()
        notifier.send_message("🔒 *Accès restreint* : Seuls les administrateurs peuvent gérer les utilisateurs.", token=token, chat_id=str(chat_id))
        return

    users = db.get_all_users(conn)
    conn.close()

    text = "👥 *Gestion des utilisateurs autorisés*\n\n"
    if super_admin_id:
        text += f"• 👑 Super Admin : `{super_admin_id}` (Propriétaire principal)\n"

    if users:
        for u in users:
            role_icon = "👑 Admin" if u["role"] == "admin" else "👤 Membre"
            text += f"• {role_icon} : *{u['name']}* (`{u['chat_id']}`)\n"
    else:
        text += "_Aucun sous-utilisateur enregistré pour le moment._\n"

    text += (
        "\n🔗 *Pour inviter par lien Telegram :*\n"
        "Tapez simplement `/invite` pour générer un lien d'invitation cliquable.\n\n"
        "➕ *Pour ajouter manuellement par ID :*\n"
        "`/invite <CHAT_ID> <Nom>`\n\n"
        "➖ *Pour révoquer un accès :*\n"
        "`/revoke <CHAT_ID>`"
    )
    notifier.send_message(text, token=token, chat_id=str(chat_id), reply_markup=notifier.get_main_reply_keyboard(is_admin_user=True))


def handle_invite_command(token: str, chat_id: str | int, text: str, db_path: str, super_admin_id: str | None) -> None:
    """Generate a shareable Telegram invite link or add user by Chat ID (Admin only)."""
    conn = db.get_connection(db_path)
    if not db.is_admin(conn, chat_id, super_admin_id):
        conn.close()
        notifier.send_message("🔒 *Accès restreint* : Seuls les administrateurs peuvent inviter des membres.", token=token, chat_id=str(chat_id))
        return

    parts = text.split()

    # If no argument given: generate shareable Deep Link!
    if len(parts) == 1:
        invite_token = db.create_invite_token(conn, chat_id)
        conn.close()
        bot_username = get_bot_username(token)
        if bot_username:
            invite_link = f"https://t.me/{bot_username}?start=invite_{invite_token}"
        else:
            invite_link = f"https://t.me/your_bot?start=invite_{invite_token}"

        notifier.send_message(
            f"🔗 *Lien d'invitation généré !*\n\n"
            f"Transmettez ce lien à la personne que vous souhaitez inviter :\n\n"
            f"👉 {invite_link}\n\n"
            f"💡 *Comment ça marche ?*\n"
            f"Dès que la personne cliquera sur ce lien et appuiera sur *Démarrer*, elle sera immédiatement autorisée et recevra les alertes !",
            token=token, chat_id=str(chat_id)
        )
        return

    # Manual addition: /invite <CHAT_ID> <Nom>
    if len(parts) < 3 or not parts[1].isdigit():
        conn.close()
        notifier.send_message("⚠️ Syntaxe : Tapez `/invite` pour un lien, ou `/invite <CHAT_ID> <Nom>` pour l'ajout manuel.", token=token, chat_id=str(chat_id))
        return

    target_chat_id = parts[1].strip()
    target_name = " ".join(parts[2:]).strip()

    db.add_user(conn, int(target_chat_id), target_name, role="user")
    conn.close()

    notifier.send_message(
        f"✅ *Utilisateur autorisé avec succès !*\n\n"
        f"• Nom : *{target_name}*\n"
        f"• Chat ID : `{target_chat_id}`\n"
        f"• Rôle : Membre\n\n"
        f"Cet utilisateur peut maintenant interagir avec le bot et recevoir les alertes !",
        token=token, chat_id=str(chat_id)
    )
    notifier.send_message(
        f"🎉 *Bonjour {target_name} !*\nVous avez été invité(e) sur le bot **PhD Scraper**. Tapez /start pour ouvrir votre menu.",
        token=token, chat_id=target_chat_id, reply_markup=notifier.get_main_reply_keyboard(is_admin_user=False)
    )


def handle_revoke_command(token: str, chat_id: str | int, text: str, db_path: str, super_admin_id: str | None) -> None:
    """Revoke authorization for a user (Admin only)."""
    conn = db.get_connection(db_path)
    if not db.is_admin(conn, chat_id, super_admin_id):
        conn.close()
        notifier.send_message("🔒 *Accès restreint* : Seuls les administrateurs peuvent révoquer des membres.", token=token, chat_id=str(chat_id))
        return

    parts = text.split()
    if len(parts) < 2:
        conn.close()
        notifier.send_message("⚠️ Format incorrect. Syntaxe : `/revoke <CHAT_ID>`", token=token, chat_id=str(chat_id))
        return

    target_chat_id = parts[1].strip()
    if not target_chat_id.isdigit():
        conn.close()
        notifier.send_message("❌ Le Chat ID doit être numérique.", token=token, chat_id=str(chat_id))
        return

    removed = db.remove_user(conn, int(target_chat_id))
    conn.close()

    if removed:
        notifier.send_message(f"✅ Accès révoqué pour l'utilisateur ID `{target_chat_id}`.", token=token, chat_id=str(chat_id))
    else:
        notifier.send_message(f"ℹ️ Aucun utilisateur trouvé avec l'ID `{target_chat_id}`.", token=token, chat_id=str(chat_id))


def process_update(update: dict[str, Any], token: str, db_path: str, load_scrapers_func: Any) -> None:
    """Dispatch incoming Telegram update (Message or Callback Query)."""
    super_admin_id = os.environ.get("TELEGRAM_CHAT_ID")

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
        if not db.is_user_authorized(conn, chat_id, super_admin_id):
            conn.close()
            answer_callback_query(token, cb_id, "🔒 Accès non autorisé")
            return

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
    # 2. Handle Shared Contact, User Picker, & Messages
    msg = update.get("message", {})
    chat_id = msg.get("chat", {}).get("id")

    if not chat_id:
        return

    if "user_shared" in msg or "contact" in msg:

        conn = db.get_connection(db_path)
        if not db.is_admin(conn, chat_id, super_admin_id):
            conn.close()
            notifier.send_message("🔒 *Accès restreint* : Seuls les administrateurs peuvent inviter des contacts.", token=token, chat_id=str(chat_id))
            return

        target_user_id = None
        target_name = "Membre"

        if "user_shared" in msg:
            target_user_id = msg["user_shared"].get("user_id")
        elif "contact" in msg:
            c = msg["contact"]
            target_user_id = c.get("user_id")
            first_name = c.get("first_name", "")
            last_name = c.get("last_name", "")
            target_name = f"{first_name} {last_name}".strip() or "Membre"

        if not target_user_id:
            conn.close()
            notifier.send_message("⚠️ Impossible de récupérer l'identifiant Telegram de ce contact.", token=token, chat_id=str(chat_id))
            return

        db.add_user(conn, int(target_user_id), target_name, role="user")
        conn.close()

        notifier.send_message(
            f"📱 *Contact ajouté et autorisé avec succès !*\n\n"
            f"• Nom : *{target_name}*\n"
            f"• Telegram ID : `{target_user_id}`\n"
            f"• Statut : Autorisé ✅\n\n"
            f"Cet utilisateur est immédiatement autorisé et recevra les futures alerte d'offres PhD !",
            token=token, chat_id=str(chat_id), reply_markup=notifier.get_main_reply_keyboard(is_admin_user=True)
        )
        notifier.send_message(
            f"🎉 *Bonjour {target_name} !*\nVous avez été invité(e) et autorisé(e) sur le bot **PhD Scraper**. Tapez /start pour ouvrir votre menu !",
            token=token, chat_id=str(target_user_id), reply_markup=notifier.get_main_reply_keyboard(is_admin_user=False)
        )
        return

    text = msg.get("text", "").strip()
    if not text:
        return

    text_lower = text.lower()

    # Handle Deep Link Start (/start invite_<token>)
    if text_lower.startswith("/start invite_") or text_lower.startswith("start invite_"):
        token_str = text.split("invite_")[-1].strip()
        user_name = msg.get("from", {}).get("first_name", "Membre")

        conn = db.get_connection(db_path)
        consumed = db.validate_and_consume_token(conn, token_str, chat_id, user_name)
        conn.close()

        if consumed:
            welcome_msg = (
                f"🎉 *Bienvenue {user_name} !*\n\n"
                "Votre accès au bot **PhD Scraper** a été activé avec succès via le lien d'invitation !\n\n"
                "Tapez /help ou utilisez les boutons ci-dessous pour explorer les offres doctorales."
            )
            notifier.send_message(welcome_msg, token=token, chat_id=str(chat_id), reply_markup=notifier.get_main_reply_keyboard(is_admin_user=False))

            admin_target = super_admin_id or str(chat_id)
            notifier.send_message(
                f"🎉 *Nouvel utilisateur rejoint !*\n\n*{user_name}* (ID: `{chat_id}`) vient de rejoindre le bot via votre lien d'invitation !",
                token=token, chat_id=str(admin_target)
            )
            return
        else:
            notifier.send_message("⚠️ *Lien d'invitation invalide ou déjà utilisé.* Veuillez demander un nouveau lien à l'administrateur.", token=token, chat_id=str(chat_id))
            return

    conn = db.get_connection(db_path)
    authorized = db.is_user_authorized(conn, chat_id, super_admin_id)
    admin_user = db.is_admin(conn, chat_id, super_admin_id)

    # Auto update user first name if available
    user_first_name = msg.get("from", {}).get("first_name")
    if user_first_name and authorized:
        db.add_user(conn, chat_id, user_first_name, role="admin" if admin_user else "user")

    conn.close()

    if not authorized:
        logger.warning("Ignored message from unauthorized chat_id: %s", chat_id)
        unauth_msg = (
            "🔒 *Accès restreint*\n\n"
            f"Votre Chat ID est : `{chat_id}`\n"
            "Transmettez cet ID à l'administrateur du bot pour obtenir l'accès aux offres doctorales."
        )
        notifier.send_message(unauth_msg, token=token, chat_id=str(chat_id))
        return

    first_word = text_lower.split()[0]

    if text_lower in ["/start", "/help", "❓ aide", "aide", "help"]:
        handle_help_command(token, chat_id, is_admin_user=admin_user)
    elif text_lower in ["/scan", "🔍 scanner", "scanner", "scan"]:
        handle_scan_command(token, chat_id, db_path, load_scrapers_func)
    elif text_lower in ["/latest", "/list", "📋 offres (5)", "offres", "latest"]:
        handle_latest_command(token, chat_id, db_path)
    elif text_lower in ["/stats", "📊 stats", "stats", "statistiques"]:
        handle_stats_command(token, chat_id, db_path)
    elif text_lower in ["/users", "👥 utilisateurs", "utilisateurs", "users"]:
        handle_users_command(token, chat_id, db_path, super_admin_id)
    elif first_word == "/invite":
        handle_invite_command(token, chat_id, text, db_path, super_admin_id)
    elif first_word == "/revoke":
        handle_revoke_command(token, chat_id, text, db_path, super_admin_id)
    else:
        handle_help_command(token, chat_id, is_admin_user=admin_user)




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

