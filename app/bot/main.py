"""Poll loop + the once-a-minute scheduler tick.

Without PERSONAL_BOT_TOKEN this idles instead of crash-looping: the compose
service is deployed before Bektas has issued a token, and an exiting container
under `restart: unless-stopped` would spin forever.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime

from app.bot import copy, review, scheduler, weekly
from app.bot.client import TelegramClient, TelegramError
from app.bot.handlers import handle_callback, handle_message
from app.database import SessionLocal
from app.services import review as review_svc
from app.services import weekly as weekly_svc
from app.services.calendar import ASTANA

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("bot")

IDLE_SECONDS = 3600
TICK_SECONDS = 60


def _owner_id() -> int | None:
    raw = os.getenv("PERSONAL_BOT_OWNER_ID", "").strip()
    return int(raw) if raw.isdigit() else None


def _digest_enabled() -> bool:
    return os.getenv("PERSONAL_BOT_MORNING_DIGEST", "true").lower() != "false"


def _weekly_enabled() -> bool:
    return os.getenv("PERSONAL_BOT_WEEKLY_DIGEST", "true").lower() != "false"


def _idle(reason: str) -> None:
    log.warning("Personal bot NOT started: %s. The website is unaffected.", reason)
    log.warning("Set PERSONAL_BOT_TOKEN in .env and restart this service to activate it.")
    while True:  # stay up, do nothing — see the module docstring
        time.sleep(IDLE_SECONDS)


def run() -> None:
    token = os.getenv("PERSONAL_BOT_TOKEN", "").strip()
    owner = _owner_id()

    if not token:
        _idle("PERSONAL_BOT_TOKEN is not set")
        return
    if owner is None:
        _idle("PERSONAL_BOT_OWNER_ID is not set or not numeric")
        return

    tg = TelegramClient(token)
    try:
        me = tg.get_me()
        log.info("Personal bot started as @%s, locked to owner %s", me.get("username"), owner)
    except TelegramError as exc:
        _idle(f"the token was rejected by Telegram ({exc})")
        return

    offset: int | None = None
    last_tick = 0.0

    while True:
        try:
            updates = tg.get_updates(offset)
        except TelegramError as exc:
            log.warning("getUpdates failed, retrying: %s", exc)
            time.sleep(5)
            continue

        for update in updates or []:
            offset = update["update_id"] + 1
            try:
                _dispatch(tg, owner, update)
            except Exception:  # noqa: BLE001 — one bad update must not stop the loop
                log.exception("update %s failed", update.get("update_id"))

        if time.time() - last_tick >= TICK_SECONDS:
            last_tick = time.time()
            try:
                _tick(tg, owner)
            except Exception:  # noqa: BLE001
                log.exception("scheduler tick failed")


def _dispatch(tg: TelegramClient, owner: int, update: dict) -> None:
    message = update.get("message")
    callback = update.get("callback_query")

    sender = ((message or callback or {}).get("from") or {}).get("id")
    chat_id = (
        (message or {}).get("chat", {}).get("id")
        or ((callback or {}).get("message") or {}).get("chat", {}).get("id")
    )

    # Owner-locked. Anyone else gets one polite line and is logged.
    if sender != owner:
        log.warning("refused stranger id=%s username=%s", sender,
                    ((message or callback or {}).get("from") or {}).get("username"))
        if chat_id:
            tg.send_message(chat_id, copy.REFUSED)
        return

    db = SessionLocal()
    try:
        if message:
            handle_message(db, tg, message, chat_id)
        elif callback:
            handle_callback(db, tg, callback, chat_id)
    finally:
        db.close()


def _tick(tg: TelegramClient, owner: int) -> None:
    """Fire due reminders, the morning digest and the evening review."""
    now = datetime.now(ASTANA)
    db = SessionLocal()
    try:
        for due in scheduler.due_reminders(scheduler.pending_events(db, now), now):
            tg.send_message(owner, copy.reminder_fire(due.title, due.starts_at))
            # Marked only after the send, so a failure retries next minute.
            scheduler.mark_fired(db, due.event_id, now)

        if _digest_enabled() and scheduler.should_send_digest(now, scheduler.last_digest_day(db)):
            tg.send_message(owner, scheduler.digest_message(db, now))
            scheduler.record_digest_sent(db, now)

        if scheduler.should_send_review(
            now, scheduler.last_review_day(db), review_svc.get_review_time(db)
        ):
            # A day with nothing on the calendar sends nothing — but it still
            # counts as "asked", so the empty day is not retried every minute.
            review.send_review(db, tg, owner, now.strftime("%Y-%m-%d"))
            scheduler.record_review_sent(db, now)

        if _weekly_enabled() and scheduler.should_send_weekly(
            now, scheduler.last_weekly_day(db), weekly_svc.get_digest_time(db)
        ):
            # This one always sends, even on a week with nothing recorded —
            # closing the week is the point. The AI paragraph is optional and
            # its failure is swallowed well below here.
            weekly.send_weekly(db, tg, owner, now)
            scheduler.record_weekly_sent(db, now)
    finally:
        db.close()
