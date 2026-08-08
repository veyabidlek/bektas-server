"""Reminder delivery and the morning digest.

The scheduling decision — "which of these should fire now?" — is a pure
function so it can be tested without a clock, a database or Telegram.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.calendar import CalendarEvent
from app.models.task import Task
from app.services.calendar import ASTANA
from app.services.settings import get_setting, set_setting

log = logging.getLogger("bot.scheduler")

# A reminder more than this far past its moment is stale — after a long outage
# Bektas should not be buried in pings for things that already happened.
MAX_LATE = timedelta(hours=6)

DIGEST_HOUR = 8
DIGEST_SETTING = "bot_last_digest_day"


@dataclass
class DueReminder:
    event_id: str
    title: str
    starts_at: str


def fire_time(starts_at: str, reminder_minutes: int | None) -> datetime | None:
    """When the ping for this event should go out, or None if it has no reminder."""
    if reminder_minutes is None:
        return None
    try:
        moment = datetime.fromisoformat(starts_at)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ASTANA)
    return moment - timedelta(minutes=reminder_minutes)


def due_reminders(events, now: datetime) -> list[DueReminder]:
    """Events whose reminder is due and has not already been sent.

    `events` is anything with starts_at / reminder_minutes / reminder_fired_at,
    so tests can pass plain objects.
    """
    due: list[DueReminder] = []

    for event in events:
        if getattr(event, "reminder_fired_at", None):
            continue  # already pinged — restarts must not double-send

        when = fire_time(event.starts_at, event.reminder_minutes)
        if when is None:
            continue

        # All-day events have a date, not a time; fromisoformat gives midnight,
        # which is the right moment to ping about them.
        if when > now:
            continue
        if now - when > MAX_LATE:
            continue

        due.append(
            DueReminder(event_id=event.id, title=event.title, starts_at=event.starts_at)
        )

    return due


def should_send_digest(now: datetime, last_sent_day: str | None) -> bool:
    """One digest per day, at or after 08:00 Almaty, never twice."""
    today = now.strftime("%Y-%m-%d")
    if last_sent_day == today:
        return False
    return now.hour >= DIGEST_HOUR


# --- database-facing wrappers ---


def pending_events(db: Session, now: datetime) -> list[CalendarEvent]:
    """Events that could plausibly be due — a cheap window, not the whole table."""
    horizon = (now + timedelta(days=2)).strftime("%Y-%m-%d")
    floor = (now - timedelta(days=2)).strftime("%Y-%m-%d")
    return (
        db.query(CalendarEvent)
        .filter(
            CalendarEvent.reminder_minutes.isnot(None),
            CalendarEvent.reminder_fired_at.is_(None),
            CalendarEvent.starts_at >= floor,
            CalendarEvent.starts_at <= horizon + "T23:59:59+05:00",
        )
        .all()
    )


def mark_fired(db: Session, event_id: str, now: datetime) -> None:
    event = db.query(CalendarEvent).filter(CalendarEvent.id == event_id).first()
    if event:
        event.reminder_fired_at = now.isoformat()
        db.commit()


def digest_lines(db: Session, now: datetime) -> list[str]:
    """Today's tasks and events, as the morning message."""
    from app.bot import copy

    today = now.strftime("%Y-%m-%d")
    lines: list[str] = []

    open_tasks = [
        t
        for t in db.query(Task).filter(Task.done == False).all()  # noqa: E712
        if t.due_at
    ]
    overdue = sorted([t for t in open_tasks if t.due_at[:10] < today], key=lambda t: t.due_at)
    due_today = sorted([t for t in open_tasks if t.due_at[:10] == today], key=lambda t: t.due_at)

    events = (
        db.query(CalendarEvent)
        .filter(CalendarEvent.starts_at >= today, CalendarEvent.starts_at < today + "T23:59:59")
        .order_by(CalendarEvent.starts_at.asc())
        .all()
    )
    # An all-day event's starts_at is just the date, so the range above misses it.
    all_day = db.query(CalendarEvent).filter(CalendarEvent.starts_at == today).all()
    events = list({e.id: e for e in events + all_day}.values())
    events.sort(key=lambda e: e.starts_at)

    if overdue:
        lines.append(copy.DIGEST_OVERDUE)
        lines += [f"• {t.title} ({t.due_at[:10]})" for t in overdue[:5]]
    if due_today:
        lines.append(copy.DIGEST_TASKS)
        lines += [f"• {t.title}" for t in due_today[:8]]
    if events:
        lines.append(copy.DIGEST_EVENTS)
        for event in events[:8]:
            when = event.starts_at[11:16] if len(event.starts_at) >= 16 else "күні бойы"
            lines.append(f"• {when} {event.title}")

    return lines


def record_digest_sent(db: Session, now: datetime) -> None:
    set_setting(db, DIGEST_SETTING, now.strftime("%Y-%m-%d"))


def last_digest_day(db: Session) -> str | None:
    return get_setting(db, DIGEST_SETTING)
