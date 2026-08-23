"""What actually happened in a week, and what the next one holds.

Storage and lookup only — the arithmetic is the pure `week_stats.py`, the same
split the evening review uses (`review.py` / `review_score.py`).

Every timestamp in this database is either "YYYY-MM-DD" or an ISO datetime
carrying the Almaty offset, and both shapes sort as text, so a window is two
string comparisons: `>= monday` and `< the Monday after`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.calendar import CalendarEvent
from app.models.diary import DiaryEntry
from app.models.inbox import InboxItem
from app.models.task import Task
from app.services import review as review_svc
from app.services.settings import get_setting, set_setting
from app.services.week_stats import Week, WeekStats, next_week, summarize_week

#: When the Sunday digest goes out, Almaty. Editable on the calendar page, the
#: same shape as `bot_review_time`.
DIGEST_TIME_KEY = "bot_weekly_digest_time"
DEFAULT_DIGEST_TIME = "20:00"

#: How much of the week's own writing the summary is allowed to see. Enough to
#: recognise the week, short enough that the prompt stays cheap.
CONTENT_LIMIT = 12


def stats_for(db: Session, week: Week) -> WeekStats:
    scores = review_svc.day_scores(db, week.days)
    return summarize_week(
        week,
        scores,
        tasks_done=_count(db, Task, Task.done_at, week),
        tasks_added=_count(db, Task, Task.created_at, week),
        diary_days=_diary_days(db, week),
        inbox_captured=_count(db, InboxItem, InboxItem.created_at, week),
        inbox_triaged=_count(db, InboxItem, InboxItem.triaged_at, week),
    )


def _count(db: Session, model, column, week: Week) -> int:
    return (
        db.query(model)
        .filter(column.isnot(None), column >= week.start, column < week.after)
        .count()
    )


def _diary_days(db: Session, week: Week) -> int:
    """Days he actually wrote on. An empty row is a day he opened, not wrote."""
    entries = (
        db.query(DiaryEntry)
        .filter(DiaryEntry.day >= week.start, DiaryEntry.day <= week.end)
        .all()
    )
    return sum(1 for e in entries if (e.body_md or "").strip() or (e.title or "").strip())


# --- what the week was about, in his own words -----------------------------


@dataclass(frozen=True)
class WeekContent:
    """Real titles and lines from the week — the only thing the summary sees."""

    diary: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.diary or self.tasks or self.events)


def _first_line(entry: DiaryEntry) -> str:
    """The entry's title, or the first line of what he wrote that day."""
    if (entry.title or "").strip():
        return entry.title.strip()
    for line in (entry.body_md or "").splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:160]
    return ""


def content_for(db: Session, week: Week) -> WeekContent:
    entries = (
        db.query(DiaryEntry)
        .filter(DiaryEntry.day >= week.start, DiaryEntry.day <= week.end)
        .order_by(DiaryEntry.day.asc())
        .all()
    )
    diary = [f"{e.day}: {line}" for e in entries if (line := _first_line(e))]

    done = (
        db.query(Task)
        .filter(Task.done_at.isnot(None), Task.done_at >= week.start, Task.done_at < week.after)
        .order_by(Task.done_at.asc())
        .all()
    )

    events = (
        db.query(CalendarEvent)
        .filter(CalendarEvent.starts_at >= week.start, CalendarEvent.starts_at < week.after)
        .order_by(CalendarEvent.starts_at.asc())
        .all()
    )

    return WeekContent(
        diary=diary[-CONTENT_LIMIT:],
        tasks=[t.title for t in done][-CONTENT_LIMIT:],
        events=[e.title for e in events][-CONTENT_LIMIT:],
    )


# --- the week ahead --------------------------------------------------------


@dataclass(frozen=True)
class WeekAhead:
    week: Week
    #: (starts_at, title) in clock order — the shape the copy layer formats.
    events: list[tuple[str, str]] = field(default_factory=list)
    event_count: int = 0
    tasks: list[str] = field(default_factory=list)
    task_count: int = 0


def ahead(db: Session, week: Week, limit: int = 5) -> WeekAhead:
    """Next week: the first few events and what is due, with the full counts."""
    upcoming = next_week(week)

    events = (
        db.query(CalendarEvent)
        .filter(CalendarEvent.starts_at >= upcoming.start, CalendarEvent.starts_at < upcoming.after)
        .order_by(CalendarEvent.starts_at.asc())
        .all()
    )
    due = (
        db.query(Task)
        .filter(
            Task.done == False,  # noqa: E712 — SQLAlchemy needs the comparison
            # An archived task is one he has decided not to do. Naming it in
            # "the week ahead" would be the digest arguing with that decision.
            # Note the CONTRAST with the completed list above, which does not
            # filter: something finished and then archived was still finished
            # this week, and the digest should say so.
            Task.archived_at.is_(None),
            Task.due_at.isnot(None),
            Task.due_at >= upcoming.start,
            Task.due_at < upcoming.after,
        )
        .order_by(Task.due_at.asc())
        .all()
    )

    return WeekAhead(
        week=upcoming,
        events=[(e.starts_at, e.title) for e in events[:limit]],
        event_count=len(events),
        tasks=[t.title for t in due[:limit]],
        task_count=len(due),
    )


# --- when the digest goes out ----------------------------------------------


def get_digest_time(db: Session) -> str:
    stored = get_setting(db, DIGEST_TIME_KEY)
    if not stored:
        return DEFAULT_DIGEST_TIME
    try:
        return review_svc.normalize_time(stored)
    except ValueError:
        return DEFAULT_DIGEST_TIME


def set_digest_time(db: Session, value: str) -> str:
    normalized = review_svc.normalize_time(value)
    set_setting(db, DIGEST_TIME_KEY, normalized)
    return normalized
