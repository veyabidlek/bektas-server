"""What the bot does with a message or a button press.

Everything routes through the phase-2 inbox and its triage service, so the bot
adds a doorway rather than a second implementation of the same rules.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.bot import copy, diary, review, scheduler, weekly
from app.bot.client import TelegramClient, button
from app.services import inbox as inbox_svc
from app.services import inbox_triage as triage
from app.services.calendar import ASTANA
from app.services.reminder_parser import parse_reminder

log = logging.getLogger("bot.handlers")

SOURCE = "telegram"


def _triage_buttons(item_id: str) -> list[list[dict]]:
    return [
        [
            button(copy.BTN_TASK, f"k:task:{item_id}"),
            button(copy.BTN_EVENT, f"k:event:{item_id}"),
        ],
        [
            button(copy.BTN_ARTICLE, f"g:article:{item_id}"),
            button(copy.BTN_DIARY, f"g:diary:{item_id}"),
            button(copy.BTN_DISMISS, f"g:dismissed:{item_id}"),
        ],
    ]


def _forward_origin(message: dict) -> str | None:
    """Who a forwarded message came from, when Telegram says."""
    origin = message.get("forward_origin") or {}
    kind = origin.get("type")

    if kind == "user":
        user = origin.get("sender_user") or {}
        name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")]))
        return name or user.get("username")
    if kind == "chat":
        return (origin.get("sender_chat") or {}).get("title")
    if kind == "channel":
        return (origin.get("chat") or {}).get("title")
    if kind == "hidden_user":
        return origin.get("sender_user_name")

    # Older Bot API shapes.
    legacy = message.get("forward_from") or {}
    if legacy:
        return " ".join(filter(None, [legacy.get("first_name"), legacy.get("last_name")]))
    return (message.get("forward_from_chat") or {}).get("title")


def handle_message(db: Session, tg: TelegramClient, message: dict, chat_id: int) -> None:
    text = (message.get("text") or message.get("caption") or "").strip()
    photos = message.get("photo") or []

    if text.startswith("/"):
        _handle_command(db, tg, chat_id, text)
        return

    # A tap on the persistent keyboard arrives as plain text equal to the label.
    # Match it here — BEFORE any capture — so a tap runs its flow and is never
    # filed into the Inbox as a note.
    if text in copy.MENU_LABELS and not photos:
        _handle_menu(db, tg, chat_id, text)
        return

    # A reply quoting one of the bot's prompts is matched by its tag — BEFORE any
    # capture — so a diary write or a review note never lands in the Inbox.
    if message.get("reply_to_message"):
        if diary.save_reply(db, tg, chat_id, message):
            return
        if review.save_note(db, tg, chat_id, message):
            return

    origin = _forward_origin(message)
    if origin:
        # Keep the provenance — a forwarded link is half-useless without it.
        text = f"↪️ {origin}:\n{text}" if text else f"↪️ {origin}"

    # A reminder becomes a calendar event straight away; everything else lands
    # in the inbox for triage.
    if text and not photos:
        reminder = parse_reminder(text, datetime.now(ASTANA))
        if reminder:
            _create_reminder(db, tg, chat_id, reminder, text)
            return

    if not text and not photos:
        return

    item = inbox_svc.create_item(db, text, source=SOURCE)

    saved_photo = False
    if photos:
        # Telegram sends several sizes; the last is the largest.
        data = tg.download_file(photos[-1]["file_id"])
        if data:
            inbox_svc.add_image(db, item, data, "image/jpeg")
            saved_photo = True

    ack = copy.CAPTURED_PHOTO if saved_photo else copy.CAPTURED
    tg.send_message(
        chat_id,
        f"{ack}\n{copy.TRIAGE_PROMPT}",
        buttons=_triage_buttons(item.id),
        reply_to=message.get("message_id"),
    )


def _handle_command(db: Session, tg: TelegramClient, chat_id: int, text: str) -> None:
    command = text.split()[0].split("@")[0].lower()
    if command in ("/start", "/help"):
        # The /start reply is what first raises the persistent keyboard.
        tg.send_message(chat_id, copy.START, keyboard=copy.MENU_KEYBOARD)
    elif command == "/review":
        # On demand, whatever the clock says — and silent on an empty day, the
        # same rule the scheduled one follows.
        if not review.send_review(db, tg, chat_id):
            tg.send_message(chat_id, copy.REVIEW_NOTHING, keyboard=copy.MENU_KEYBOARD)
    elif command == "/digest":
        # The Sunday message, for the week he is currently in. Unlike /review
        # this always answers: a quiet week is still an answer.
        weekly.send_weekly(db, tg, chat_id)
    else:
        tg.send_message(chat_id, copy.UNKNOWN_COMMAND, keyboard=copy.MENU_KEYBOARD)


def _handle_menu(db: Session, tg: TelegramClient, chat_id: int, label: str) -> None:
    """A tap on the persistent keyboard — routed to the same flows as the
    commands, reusing existing builders. Each reasserts the keyboard so it stays."""
    if label == copy.BTN_MENU_REVIEW:
        if not review.send_review(db, tg, chat_id):
            tg.send_message(chat_id, copy.REVIEW_NOTHING, keyboard=copy.MENU_KEYBOARD)
    elif label == copy.BTN_MENU_WEEK:
        weekly.send_weekly(db, tg, chat_id)
    elif label == copy.BTN_MENU_TODAY:
        # The morning-digest view, on demand — reuses the scheduler's builder.
        message = scheduler.digest_message(db, datetime.now(ASTANA))
        tg.send_message(chat_id, message, keyboard=copy.MENU_KEYBOARD)
    elif label == copy.BTN_MENU_INBOX:
        items = inbox_svc.list_items(db, triaged=False)
        tg.send_message(chat_id, copy.inbox_list(items), keyboard=copy.MENU_KEYBOARD)
    elif label == copy.BTN_MENU_DIARY:
        diary.show_today(db, tg, chat_id)


def _create_reminder(db, tg, chat_id, reminder, original: str) -> None:
    from app.schemas.calendar import CalendarEventCreate
    from app.services import calendar as calendar_svc

    event = calendar_svc.create_event(
        db,
        CalendarEventCreate(
            title=reminder.title,
            starts_at=reminder.starts_at,
            reminder_minutes=reminder.reminder_minutes,
        ),
    )
    tg.send_message(
        chat_id,
        copy.event_confirmation(
            reminder.title, reminder.starts_at, reminder.reminder_minutes
        ),
        buttons=[
            [
                button(copy.BTN_CONFIRM, f"rc:{event.id}"),
                button(copy.BTN_EDIT, f"rx:{event.id}"),
            ]
        ],
    )


def handle_callback(db: Session, tg: TelegramClient, query: dict, chat_id: int) -> None:
    data = query.get("data") or ""
    message = query.get("message") or {}
    message_id = message.get("message_id")
    callback_id = query.get("id")

    # g:<kind>:<item>  → triage straight through
    # k:<kind>:<item>  → ask the one extra question first
    # d:<kind>:<item>:<when> → the answer to that question
    # rc / rx          → confirm or undo a parsed reminder
    # ro:<outcome>:<event>   → an evening-review answer
    # rn:<event>:<card>      → add a note to that answer
    # rv:<day>               → finish the review, send the score
    parts = data.split(":")
    action = parts[0]

    try:
        if action == "g" and len(parts) == 3:
            _do_triage(db, tg, chat_id, message_id, callback_id, parts[2], parts[1])

        elif action == "k" and len(parts) == 3:
            _ask_when(tg, chat_id, message_id, callback_id, parts[1], parts[2])

        elif action == "d" and len(parts) == 4:
            _do_triage(
                db, tg, chat_id, message_id, callback_id, parts[2], parts[1], parts[3]
            )

        elif action == "rc":
            tg.answer_callback(callback_id, copy.DONE_EVENT)

        elif action == "rx" and len(parts) == 2:
            _undo_reminder(db, tg, chat_id, message_id, callback_id, parts[1])

        elif action == "ro" and len(parts) == 3:
            review.record(db, tg, chat_id, message_id, callback_id, parts[2], parts[1])

        elif action == "rn" and len(parts) in (2, 3):
            _ask_review_note(db, tg, chat_id, callback_id, parts)

        elif action == "rv" and len(parts) == 2:
            tg.answer_callback(callback_id)
            review.send_score(db, tg, chat_id, parts[1])

        else:
            tg.answer_callback(callback_id)
    except Exception:  # noqa: BLE001 — one bad press must not stop the bot
        log.exception("callback %s failed", data)
        tg.answer_callback(callback_id, copy.FAILED)


def _ask_review_note(db, tg, chat_id, callback_id, parts: list[str]) -> None:
    from app.services import calendar as calendar_svc

    event = calendar_svc.get_event(db, parts[1])
    if not event:
        tg.answer_callback(callback_id, copy.FAILED)
        return
    card_message_id = int(parts[2]) if len(parts) == 3 and parts[2].isdigit() else None
    review.ask_note(tg, chat_id, callback_id, event.title, event.id, card_message_id)


def _ask_when(tg, chat_id, message_id, callback_id, kind: str, item_id: str) -> None:
    """Task wants a due date, event wants a moment. Buttons, not a conversation."""
    tg.answer_callback(callback_id)

    if kind == "task":
        options = [
            button(copy.BTN_TODAY, f"d:task:{item_id}:today"),
            button(copy.BTN_TOMORROW, f"d:task:{item_id}:tomorrow"),
            button(copy.BTN_WEEK, f"d:task:{item_id}:week"),
        ]
        prompt = copy.WHEN_PROMPT_TASK
    else:
        options = [
            button("Today 18:00", f"d:event:{item_id}:today18"),
            button("Tomorrow 09:00", f"d:event:{item_id}:tom09"),
            button("Tomorrow 18:00", f"d:event:{item_id}:tom18"),
        ]
        prompt = copy.WHEN_PROMPT_EVENT

    tg.send_message(chat_id, prompt, buttons=[options])


def _when_to_values(when: str) -> dict:
    """Turn a button's shorthand into the field the triage endpoint wants."""
    now = datetime.now(ASTANA)
    day = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    return {
        "today": {"due_at": day},
        "tomorrow": {"due_at": tomorrow},
        "week": {"due_at": (now + timedelta(days=7)).strftime("%Y-%m-%d")},
        "today18": {"starts_at": f"{day}T18:00:00"},
        "tom09": {"starts_at": f"{tomorrow}T09:00:00"},
        "tom18": {"starts_at": f"{tomorrow}T18:00:00"},
    }.get(when, {})


def _do_triage(
    db, tg, chat_id, message_id, callback_id, item_id: str, kind: str, when: str | None = None
) -> None:
    item = inbox_svc.get_item(db, item_id)
    if not item:
        tg.answer_callback(callback_id, copy.FAILED)
        return

    values = _when_to_values(when) if when else {}

    try:
        _, target_id = inbox_svc.triage_item(db, item, kind, **values)
    except triage.TriageError:
        tg.answer_callback(callback_id, copy.ALREADY_TRIAGED)
        return

    tg.answer_callback(callback_id)
    if message_id:
        tg.edit_message(chat_id, message_id, _confirmation(db, kind, target_id, item))


def _confirmation(db, kind: str, target_id: str | None, item) -> str:
    """The settled state a flow ends in — the site's card, as a message."""
    from app.models.calendar import CalendarEvent
    from app.models.task import Task
    from app.services import tasks as tasks_svc

    if kind == "task" and target_id:
        task = db.query(Task).filter(Task.id == target_id).first()
        if task:
            return copy.task_confirmation(task.title, task.due_at, tasks_svc.today())
    if kind == "event" and target_id:
        event = db.query(CalendarEvent).filter(CalendarEvent.id == target_id).first()
        if event:
            return copy.event_confirmation(
                event.title, event.starts_at, event.reminder_minutes
            )
    if kind == "article" and target_id:
        from app.models.article import Article

        article = db.query(Article).filter(Article.slug == target_id).first()
        if article:
            return copy.note_confirmation(article.title)
    if kind == "diary" and target_id:
        return copy.diary_confirmation(target_id)
    return copy.DONE_DISMISS


def _undo_reminder(db, tg, chat_id, message_id, callback_id, event_id: str) -> None:
    """✏️ — drop the event and keep the thought in the inbox instead."""
    from app.services import calendar as calendar_svc

    event = calendar_svc.get_event(db, event_id)
    if event:
        title = event.title
        calendar_svc.delete_event(db, event)
        inbox_svc.create_item(db, title, source=SOURCE)

    tg.answer_callback(callback_id, copy.REMINDER_CANCELLED)
    if message_id:
        tg.edit_message(chat_id, message_id, copy.REMINDER_CANCELLED)
