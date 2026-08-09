"""Write the diary from chat, and read it back article-style.

The same stateless reply-to pattern the review notes use: the prompt carries
`#diary-<day>` in its own text, so a reply quoting it tells the handler which
day to write — nothing is remembered between updates.

Reuse, not a second store: text appends to the day via `diary` service's
`upsert_entry` using the *same* `DIARY_SEPARATOR` the inbox→Diary triage uses,
and photos go through the very pipeline the site uses (`diary.add_image` —
downscale, named volume, auth-served). A direct write and an inbox-triage write
both append to today's one entry, so the two flows never double-write.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.bot import copy
from app.bot.client import TelegramClient
from app.services import diary as diary_svc
from app.services.inbox import DIARY_SEPARATOR

log = logging.getLogger("bot.diary")

# "#diary-2026-08-09" — the day this reply writes into.
DIARY_TAG = re.compile(r"#diary-(\d{4}-\d{2}-\d{2})\b")

MAX_PHOTOS_SHOWN = 10


def _read_image(db: Session, image_id: str) -> bytes | None:
    image = diary_svc.get_image(db, image_id)
    if not image:
        return None
    try:
        return diary_svc.image_path(image).read_bytes()
    except OSError as exc:
        log.warning("could not read diary image %s: %s", image_id, exc)
        return None


def show_today(db: Session, tg: TelegramClient, chat_id: int) -> None:
    """The 📔 tap: render today's entry like an article, send its photos as real
    images, then the prompt to write more."""
    day = diary_svc.today()
    entry = diary_svc.get_entry(db, day)

    tg.send_message(chat_id, copy.diary_article(entry), keyboard=copy.MENU_KEYBOARD)

    if getattr(entry, "exists", False):
        for image in entry.images[:MAX_PHOTOS_SHOWN]:
            data = _read_image(db, image.id)
            if data:
                tg.send_photo(chat_id, data, filename=f"{image.day}-{image.id}.jpg")

    tg.send_message(chat_id, copy.diary_prompt(day))


def _append_text(db: Session, day: str, text: str) -> None:
    """Add to the day, keeping earlier writing — the same separator the inbox
    triage uses, so an entry reads coherently however it was built."""
    entry = diary_svc.get_entry(db, day)
    existing = entry.body_md.strip()
    body = f"{existing}{DIARY_SEPARATOR}{text}" if existing else text
    diary_svc.upsert_entry(db, day, body, entry.title)


def save_reply(db: Session, tg: TelegramClient, chat_id: int, message: dict) -> bool:
    """Handle a reply that quotes the diary prompt. False = not one of ours."""
    quoted = message.get("reply_to_message") or {}
    match = DIARY_TAG.search(quoted.get("text") or quoted.get("caption") or "")
    if not match:
        return False

    day = match.group(1)
    body = (message.get("text") or message.get("caption") or "").strip()
    photos = message.get("photo") or []

    added_photo = False
    if photos:
        data = tg.download_file(photos[-1]["file_id"])  # last size = largest
        if data:
            diary_svc.add_image(db, day, data, "image/jpeg")
            added_photo = True

    if body:
        _append_text(db, day, body)

    if added_photo and body:
        ack = copy.DIARY_SAVED_BOTH
    elif added_photo:
        ack = copy.DIARY_PHOTO_SAVED
    elif body:
        ack = copy.DIARY_SAVED
    else:
        # A reply that quoted the prompt but carried nothing usable (a sticker,
        # say) — still ours, so nudge rather than let it fall to capture.
        ack = copy.DIARY_EMPTY_REPLY

    tg.send_message(chat_id, ack, reply_to=message.get("message_id"), keyboard=copy.MENU_KEYBOARD)
    return True
