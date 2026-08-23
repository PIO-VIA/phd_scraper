"""
Tests for Telegram Bot integration and multi-user administration module.
"""
from __future__ import annotations

import pytest
from scraper import notifier, bot, db


class TestNotifierButtons:
    def test_get_main_reply_keyboard(self):
        kb = notifier.get_main_reply_keyboard(is_admin_user=True)
        assert "keyboard" in kb
        assert len(kb["keyboard"]) == 3
        assert kb["keyboard"][0][0]["text"] == "🔍 Scanner"
        assert kb["keyboard"][2][0]["text"] == "📱 Inviter un contact"
        assert kb["keyboard"][2][1]["text"] == "👥 Utilisateurs"

    def test_get_offer_inline_keyboard(self):
        kb = notifier.get_offer_inline_keyboard(42, "https://example.com/phd")
        assert "inline_keyboard" in kb
        assert len(kb["inline_keyboard"]) == 2
        assert kb["inline_keyboard"][0][0]["callback_data"] == "apply_42"
        assert kb["inline_keyboard"][0][1]["callback_data"] == "ignore_42"
        assert kb["inline_keyboard"][1][0]["url"] == "https://example.com/phd"


class TestUserManagementDb:
    def test_add_and_remove_user(self, tmp_path):
        db_file = tmp_path / "test.db"
        db.init_db(db_file)
        conn = db.get_connection(db_file)

        assert not db.is_user_authorized(conn, 99999)
        db.add_user(conn, 99999, "Alice", role="user")
        assert db.is_user_authorized(conn, 99999)

        users = db.get_all_users(conn)
        assert len(users) == 1
        assert users[0]["name"] == "Alice"

        db.remove_user(conn, 99999)
        assert not db.is_user_authorized(conn, 99999)
        conn.close()

    def test_invite_token_flow(self, tmp_path):
        db_file = tmp_path / "test.db"
        db.init_db(db_file)
        conn = db.get_connection(db_file)

        token = db.create_invite_token(conn, 12345)
        assert len(token) == 8

        # Consume token
        success = db.validate_and_consume_token(conn, token, 77777, "Bob")
        assert success is True
        assert db.is_user_authorized(conn, 77777)

        # Cannot reuse token
        fail = db.validate_and_consume_token(conn, token, 88888, "Charlie")
        assert fail is False
        conn.close()


class TestBotHandlers:
    def test_process_update_help(self, monkeypatch, tmp_path):
        db_file = tmp_path / "test.db"
        db.init_db(db_file)
        called = {}

        def fake_send(text, token=None, chat_id=None, reply_markup=None):
            called["sent"] = True
            called["text"] = text

        monkeypatch.setattr(notifier, "send_message", fake_send)
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        update = {"message": {"chat": {"id": 12345}, "text": "/help"}}
        bot.process_update(update, "fake_token", str(db_file), None)

        assert called.get("sent") is True
        assert "PhD Scraper" in called.get("text", "")

    def test_unauthorized_user_blocked(self, monkeypatch, tmp_path):
        db_file = tmp_path / "test.db"
        db.init_db(db_file)
        called = {}

        def fake_send(text, token=None, chat_id=None, reply_markup=None):
            called["sent"] = True
            called["text"] = text

        monkeypatch.setattr(notifier, "send_message", fake_send)
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        update = {"message": {"chat": {"id": 88888}, "text": "/stats"}}
        bot.process_update(update, "fake_token", str(db_file), None)

        assert called.get("sent") is True
        assert "Accès restreint" in called.get("text", "")

    def test_deep_link_invitation(self, monkeypatch, tmp_path):
        db_file = tmp_path / "test.db"
        db.init_db(db_file)
        conn = db.get_connection(db_file)
        inv_token = db.create_invite_token(conn, 12345)
        conn.close()

        sent_messages = []

        def fake_send(text, token=None, chat_id=None, reply_markup=None):
            sent_messages.append((chat_id, text))

        monkeypatch.setattr(notifier, "send_message", fake_send)
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        update = {
            "message": {
                "chat": {"id": 654321},
                "from": {"first_name": "Dave"},
                "text": f"/start invite_{inv_token}",
            }
        }
        bot.process_update(update, "fake_token", str(db_file), None)

        assert len(sent_messages) == 2
        assert "Bienvenue Dave" in sent_messages[0][1]
        assert "Nouvel utilisateur rejoint" in sent_messages[1][1]

        conn = db.get_connection(db_file)
        assert db.is_user_authorized(conn, 654321)
        conn.close()

    def test_contact_picker_invitation(self, monkeypatch, tmp_path):
        db_file = tmp_path / "test.db"
        db.init_db(db_file)

        sent_messages = []

        def fake_send(text, token=None, chat_id=None, reply_markup=None):
            sent_messages.append((chat_id, text))

        monkeypatch.setattr(notifier, "send_message", fake_send)
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        # Admin shares a contact via button
        update = {
            "message": {
                "chat": {"id": 12345},
                "contact": {
                    "user_id": 555123,
                    "first_name": "Sophie",
                    "last_name": "Martin",
                },
            }
        }
        bot.process_update(update, "fake_token", str(db_file), None)

        assert len(sent_messages) == 2
        assert "Sophie Martin" in sent_messages[0][1]
        assert "Bonjour Sophie Martin" in sent_messages[1][1]

        conn = db.get_connection(db_path=db_file)
        assert db.is_user_authorized(conn, 555123)
        conn.close()
