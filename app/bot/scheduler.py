"""Reminder delivery, the morning digest and the evening review.

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
from app.services import review as review_svc
from app.services import weekly as weekly_svc
from app.services.calendar import ASTANA
from app.services.settings import get_setting, set_setting

log = logging.getLogger("bot.scheduler")

# A reminder more than this far past its moment is stale — after a long outage
# Bektas should not be buried in pings for things that already happened.
MAX_LATE = timedelta(hours=6)

DIGEST_HOUR = 8
DIGEST_SETTING = "bot_last_digest_day"

# The evening review, like the digest, is once a day and remembers the day it
# last went out — so a restart at 21:31 does not ask him everything twice.
REVIEW_SETTING = "bot_last_review_day"

# The weekly digest: Sunday evening, once, remembering which Sunday. Same flag
# shape again — the day string is the idempotency key everywhere in this bot.
WEEKLY_SETTING = "bot_last_weekly_day"
SUNDAY = 6


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


def should_send_review(
    now: datetime, last_sent_day: str | None, review_time: str
) -> bool:
    """One evening review per day, at or after the configured Almaty time.

    `review_time` is "HH:MM" as stored by the calendar page; nonsense in the
    setting falls back to the default rather than silencing the review.
    """
    today = now.strftime("%Y-%m-%d")
    if last_sent_day == today:
        return False
    try:
        hour, minute = (int(part) for part in review_svc.normalize_time(review_time).split(":"))
    except ValueError:
        hour, minute = (int(part) for part in review_svc.DEFAULT_REVIEW_TIME.split(":"))
    return (now.hour, now.minute) >= (hour, minute)


def should_send_weekly(
    now: datetime, last_sent_day: str | None, digest_time: str
) -> bool:
    """One weekly digest, on a Sunday, at or after the configured Almaty time.

    A Monday restart must not send Sunday's digest late: the weekday check is
    what keeps the week's boundary honest, and the day flag is what keeps a
    restart at 20:01 from sending it twice.
    """
    if now.weekday() != SUNDAY:
        return False

    today = now.strftime("%Y-%m-%d")
    if last_sent_day == today:
        return False

    try:
        hour, minute = (int(part) for part in review_svc.normalize_time(digest_time).split(":"))
    except ValueError:
        hour, minute = (
            int(part) for part in weekly_svc.DEFAULT_DIGEST_TIME.split(":")
        )
    return (now.hour, now.minute) >= (hour, minute)


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


def digest_message(db: Session, now: datetime) -> str:
    """The 08:00 message, built from the same shape the dashboard shows.

    Events timeline, then due tasks with their counts, then the inbox — so the
    bot and the site read as one product rather than two summaries.
    """
    from app.bot import copy
    from app.models.inbox import InboxItem

    today = now.strftime("%Y-%m-%d")

    open_tasks = [
        t
        for t in db.query(Task).filter(Task.done == False).all()  # noqa: E712
        if t.due_at
    ]
    overdue = [t for t in open_tasks if t.due_at[:10] < today]
    due_today = sorted([t for t in open_tasks if t.due_at[:10] == today], key=lambda t: t.due_at)

    # A timed event's starts_at carries an offset; an all-day one is just the
    # date, so both shapes have to be matched.
    events = [
        e
        for e in db.query(CalendarEvent).all()
        if e.starts_at[:10] == today
    ]
    events.sort(key=lambda e: (len(e.starts_at) <= 10 and "0" or e.starts_at[11:16]))

    timeline = [
        (e.starts_at[11:16] if len(e.starts_at) >= 16 else None, e.title) for e in events
    ]

    inbox = db.query(InboxItem).filter(InboxItem.triaged_to.is_(None)).count()

    # Yesterday's effectiveness, if he reviewed it — the morning is when that
    # number is worth reading. A day he never reviewed adds no line at all.
    yesterday = review_svc.day_score(
        db, (now - timedelta(days=1)).strftime("%Y-%m-%d")
    )

    return copy.digest(
        today_iso=today,
        events=timeline,
        tasks=[t.title for t in due_today[:8]],
        overdue=len(overdue),
        inbox=inbox,
        yesterday=yesterday if yesterday.has_data else None,
    )


def record_digest_sent(db: Session, now: datetime) -> None:
    set_setting(db, DIGEST_SETTING, now.strftime("%Y-%m-%d"))


def last_digest_day(db: Session) -> str | None:
    return get_setting(db, DIGEST_SETTING)


def record_review_sent(db: Session, now: datetime) -> None:
    set_setting(db, REVIEW_SETTING, now.strftime("%Y-%m-%d"))


def last_review_day(db: Session) -> str | None:
    return get_setting(db, REVIEW_SETTING)


def record_weekly_sent(db: Session, now: datetime) -> None:
    set_setting(db, WEEKLY_SETTING, now.strftime("%Y-%m-%d"))


def last_weekly_day(db: Session) -> str | None:
    return get_setting(db, WEEKLY_SETTING)
