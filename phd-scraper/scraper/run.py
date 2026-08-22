"""
PhD Scraper — Main entry point.

Usage:
  python -m scraper.run scan           # Full scraping cycle
  python -m scraper.run list --new     # List new (unnotified) offers
  python -m scraper.run mark <id> <status>  # Update offer status manually
  python -m scraper.run test-notify    # Send a test Telegram message
"""
from __future__ import annotations

import argparse
import importlib
import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import Type

import yaml
from dotenv import load_dotenv

# Load .env at import time so all submodules see the vars
load_dotenv()

from scraper import db, notifier, filters
from scraper.base import BaseScraper
from scraper.models import Offer

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(log_dir: str | None = None) -> None:
    log_dir_path = Path(log_dir or os.environ.get("LOG_DIR", "logs"))
    log_dir_path.mkdir(parents=True, exist_ok=True)
    log_file = log_dir_path / f"scraper_{date.today()}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source loader
# ---------------------------------------------------------------------------

def load_scrapers(sources_config: str | Path | None = None) -> list[BaseScraper]:
    config_path = Path(
        sources_config
        or Path(__file__).parent.parent / "config" / "sources.yaml"
    )
    if not config_path.exists():
        logger.error("sources.yaml not found at %s", config_path)
        return []

    with config_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    scrapers: list[BaseScraper] = []
    for entry in data.get("sources", []):
        if not entry.get("enabled", True):
            logger.info("Source '%s' is disabled — skipping.", entry.get("name"))
            continue
        module_path: str = entry["module"]
        class_name: str = entry["class"]
        try:
            mod = importlib.import_module(module_path)
            cls: Type[BaseScraper] = getattr(mod, class_name)
            scrapers.append(cls())
        except (ImportError, AttributeError) as exc:
            logger.error(
                "Could not load scraper %s.%s: %s", module_path, class_name, exc
            )
    return scrapers


# ---------------------------------------------------------------------------
# scan command
# ---------------------------------------------------------------------------

def cmd_scan(args: argparse.Namespace) -> None:
    db_path = os.environ.get("DB_PATH", "data/offers.db")
    db.init_db(db_path)
    conn = db.get_connection(db_path)

    scrapers = load_scrapers()
    if not scrapers:
        logger.error("No scrapers loaded. Exiting.")
        return

    keywords = filters.load_keywords()
    all_offers: list[Offer] = []
    ok_sources: list[str] = []
    fail_sources: list[str] = []

    for scraper in scrapers:
        logger.info("▶ Running scraper: %s", scraper.source_name)
        try:
            raw_offers = scraper.run()
            ok_sources.append(scraper.source_name)
        except Exception as exc:
            logger.error("[%s] Unexpected error in run(): %s", scraper.source_name, exc)
            fail_sources.append(scraper.source_name)
            continue

        matched = filters.filter_offers(raw_offers, keywords)
        all_offers.extend(matched)

    # Dedup + insert
    new_ids: list[int] = []
    for offer in all_offers:
        inserted = db.insert_offer(conn, offer)
        if inserted:
            # Get the just-inserted row id
            cursor = conn.execute(
                "SELECT id FROM offers WHERE url_hash = ?", (offer.url_hash,)
            )
            row = cursor.fetchone()
            if row:
                new_ids.append(row["id"])

    logger.info(
        "Scan complete: %d new offer(s) stored (from %d matched total).",
        len(new_ids), len(all_offers),
    )

    # Notify
    if new_ids:
        new_rows = [
            conn.execute("SELECT * FROM offers WHERE id = ?", (oid,)).fetchone()
            for oid in new_ids
        ]
        new_rows = [r for r in new_rows if r]
        notified_ids = notifier.send_notifications(new_rows)
        if notified_ids:
            db.mark_notified(conn, notified_ids)
            logger.info("Notified for %d offer(s).", len(notified_ids))
    else:
        logger.info("No new offers — nothing to notify.")

    conn.close()

    # Final summary
    ok_str = ", ".join(ok_sources) if ok_sources else "none"
    fail_str = ", ".join(fail_sources) if fail_sources else "none"
    total = len(ok_sources) + len(fail_sources)
    logger.info(
        "SUMMARY: %d/%d sources OK. Errors: [%s]",
        len(ok_sources), total, fail_str,
    )
    if fail_sources:
        print(f"\n⚠  {len(fail_sources)}/{total} sources failed: {fail_str}")
    else:
        print(f"\n✅  All {total} sources completed successfully.")
    print(f"   {len(new_ids)} new offer(s) found and stored.")


# ---------------------------------------------------------------------------
# list command
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> None:
    db_path = os.environ.get("DB_PATH", "data/offers.db")
    db.init_db(db_path)
    conn = db.get_connection(db_path)

    status_filter = "new" if args.new else None
    rows = db.get_all_offers(conn, status=status_filter)
    conn.close()

    if not rows:
        print("No offers found.")
        return

    print(f"\n{'ID':>4}  {'STATUS':<10}  {'SOURCE':<20}  {'TITLE'}")
    print("─" * 80)
    for row in rows:
        title = row["title"][:50] + "…" if len(row["title"]) > 50 else row["title"]
        print(f"{row['id']:>4}  {row['status']:<10}  {row['source']:<20}  {title}")
    print(f"\nTotal: {len(rows)} offer(s).")


# ---------------------------------------------------------------------------
# mark command
# ---------------------------------------------------------------------------

def cmd_mark(args: argparse.Namespace) -> None:
    db_path = os.environ.get("DB_PATH", "data/offers.db")
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    updated = db.mark_offer_status(conn, args.id, args.status)
    conn.close()
    if updated:
        print(f"✅ Offer #{args.id} marked as '{args.status}'.")
    else:
        print(f"❌ No offer found with id={args.id}.")


# ---------------------------------------------------------------------------
# test-notify command
# ---------------------------------------------------------------------------

def cmd_test_notify(args: argparse.Namespace) -> None:
    ok = notifier.send_test_message()
    if ok:
        print("✅ Test message sent to Telegram successfully.")
    else:
        print("❌ Failed to send test message. Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")


# ---------------------------------------------------------------------------
# bot command
# ---------------------------------------------------------------------------

def cmd_bot(args: argparse.Namespace) -> None:
    db_path = os.environ.get("DB_PATH", "data/offers.db")
    db.init_db(db_path)
    from scraper.bot import run_bot_polling
    run_bot_polling(db_path=db_path, load_scrapers_func=load_scrapers)


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scraper",
        description="PhD opportunity scraper — Germany, France, Europe",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("scan", help="Run a full scraping + notification cycle.")
    sub.add_parser("bot", help="Run the interactive Telegram bot daemon.")

    list_p = sub.add_parser("list", help="List stored offers.")
    list_p.add_argument(
        "--new", action="store_true", help="Show only unnotified offers."
    )

    mark_p = sub.add_parser("mark", help="Update the status of an offer.")
    mark_p.add_argument("id", type=int, help="Offer ID.")
    mark_p.add_argument(
        "status",
        choices=["new", "notified", "applied", "ignored", "expired"],
        help="New status.",
    )

    sub.add_parser("test-notify", help="Send a test Telegram message.")

    return parser


def main() -> None:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "scan": cmd_scan,
        "bot": cmd_bot,
        "list": cmd_list,
        "mark": cmd_mark,
        "test-notify": cmd_test_notify,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()

