"""The evening review: one tap per event, then the day's score.

The flow is deliberately stateless. Each answer button carries its event id,
and the note prompt carries the id in its own text — so a reply quoting that
message tells the handler everything it needs. Nothing is remembered between
updates, which is what let the triage flow survive restarts and works here for
the same reason.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.bot import copy
from app.bot.client import TelegramClient, button
from app.services import review as review_svc
from app.services.calendar import ASTANA

log = logging.getLogger("bot.review")

# "#ev-a1b2c3d4" or "#ev-a1b2c3d4-1187" — the event, and the card message to
# update once the note lands.
NOTE_TAG = re.compile(r"#ev-([0-9a-zA-Z]+?)(?:-(\d+))?\b")


def today(now: datetime | None = None) -> str:
    return (now or datetime.now(ASTANA)).strftime("%Y-%m-%d")


def _answer_buttons(event_id: str) -> list[list[dict]]:
    return [
        [
            button(copy.BTN_DONE, f"ro:done:{event_id}"),
            button(copy.BTN_PARTIAL, f"ro:partial:{event_id}"),
            button(copy.BTN_NO, f"ro:no:{event_id}"),
        ]
    ]


def send_review(db: Session, tg: TelegramClient, chat_id: int, day: str | None = None) -> bool:
    """Ask about every event of `day`. False — and silence — when there are none.

    A day with nothing on the calendar is not a day worth scoring, and a nightly
    "you had nothing on" message would be noise.
    """
    day = day or today()
    events = review_svc.events_of_day(db, day)
    if not events:
        return False

    tg.send_message(
        chat_id,
        copy.review_header(day),
        buttons=[[button(copy.BTN_FINISH, f"rv:{day}")]],
    )

    recorded = review_svc.outcomes_for(db, [e.id for e in events])
    for event in events:
        answered = recorded.get(event.id)
        # A re-run shows what he already said, with the buttons still live.
        text = (
            copy.review_settled(
                event.title, event.starts_at, answered.outcome, answered.note, event.all_day
            )
            if answered
            else copy.review_card(event.title, event.starts_at, event.all_day)
        )
        tg.send_message(chat_id, text, buttons=_answer_buttons(event.id))

    return True


def record(
    db: Session,
    tg: TelegramClient,
    chat_id: int,
    message_id: int | None,
    callback_id: str,
    event_id: str,
    outcome: str,
) -> None:
    """A tap. Records the answer and settles the message it was tapped on."""
    from app.services import calendar as calendar_svc

    event = calendar_svc.get_event(db, event_id)
    if not event:
        tg.answer_callback(callback_id, copy.FAILED)
        return

    row = review_svc.record_outcome(db, event_id, outcome)
    tg.answer_callback(callback_id, copy.RECORDED)

    if message_id:
        tg.edit_message(
            chat_id,
            message_id,
            copy.review_settled(
                event.title, event.starts_at, row.outcome, row.note, event.all_day
            ),
            buttons=[[button(copy.BTN_NOTE, f"rn:{event_id}:{message_id}")]],
        )

    # The score arrives on its own once the last event has an answer — no
    # "finish" step needed on a day he answers straight through.
    day = event.starts_at[:10]
    score = review_svc.day_score(db, day)
    if score.reviewed >= score.total and score.total:
        send_score(db, tg, chat_id, day)


def ask_note(
    tg: TelegramClient,
    chat_id: int,
    callback_id: str,
    title: str,
    event_id: str,
    card_message_id: int | None,
) -> None:
    tg.answer_callback(callback_id)
    tg.send_message(chat_id, copy.note_prompt(title, event_id, card_message_id))


def note_target(text: str | None) -> tuple[str, int | None] | None:
    """Read the event (and its card) out of a quoted note prompt."""
    if not text:
        return None
    match = NOTE_TAG.search(text)
    if not match:
        return None
    return match.group(1), int(match.group(2)) if match.group(2) else None


def save_note(
    db: Session, tg: TelegramClient, chat_id: int, message: dict
) -> bool:
    """Handle a reply that quotes a note prompt. False = not one of ours."""
    quoted = message.get("reply_to_message") or {}
    target = note_target(quoted.get("text") or quoted.get("caption"))
    if not target:
        return False

    event_id, card_message_id = target
    note = (message.get("text") or message.get("caption") or "").strip()
    if not note:
        return False

    row = review_svc.set_note(db, event_id, note)
    if not row:
        tg.send_message(chat_id, copy.NOTE_ORPHANED, reply_to=message.get("message_id"))
        return True

    from app.services import calendar as calendar_svc

    event = calendar_svc.get_event(db, event_id)
    if event and card_message_id:
        tg.edit_message(
            chat_id,
            card_message_id,
            copy.review_settled(
                event.title, event.starts_at, row.outcome, row.note, event.all_day
            ),
        )

    tg.send_message(chat_id, copy.NOTE_SAVED, reply_to=message.get("message_id"))
    return True


def send_score(db: Session, tg: TelegramClient, chat_id: int, day: str) -> None:
    score = review_svc.day_score(db, day)
    if score.percent is None:
        tg.send_message(
            chat_id, copy.REVIEW_NOTHING if not score.total else copy.REVIEW_UNANSWERED
        )
        return
    tg.send_message(
        chat_id, copy.day_score(score.done, score.partial, score.reviewed, score.percent)
    )
