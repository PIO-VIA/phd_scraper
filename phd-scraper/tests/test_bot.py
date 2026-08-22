"""
Tests for Telegram Bot integration module.
"""
from __future__ import annotations

import pytest

from scraper import notifier, bot


class TestNotifierButtons:
    def test_get_main_reply_keyboard(self):
        kb = notifier.get_main_reply_keyboard()
        assert "keyboard" in kb
        assert len(kb["keyboard"]) == 2
        assert kb["keyboard"][0][0]["text"] == "🔍 Scanner"

    def test_get_offer_inline_keyboard(self):
        kb = notifier.get_offer_inline_keyboard(42, "https://example.com/phd")
        assert "inline_keyboard" in kb
        assert len(kb["inline_keyboard"]) == 2
        assert kb["inline_keyboard"][0][0]["callback_data"] == "apply_42"
        assert kb["inline_keyboard"][0][1]["callback_data"] == "ignore_42"
        assert kb["inline_keyboard"][1][0]["url"] == "https://example.com/phd"


class TestBotHandlers:
    def test_process_update_help(self, monkeypatch):
        called = {}

        def fake_send(text, token=None, chat_id=None, reply_markup=None):
            called["sent"] = True
            called["text"] = text

        monkeypatch.setattr(notifier, "send_message", fake_send)

        update = {"message": {"chat": {"id": 12345}, "text": "/help"}}
        bot.process_update(update, "fake_token", "fake_db.db", None)

        assert called.get("sent") is True
        assert "PhD Scraper" in called.get("text", "")
