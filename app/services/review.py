"""Recording how the day's events actually went.

Storage and lookup only — the arithmetic lives in `review_score.py`, which is
pure and tested on its own. One outcome per event: answering again overwrites,
because "did I get up at 07:00?" has one true answer per day.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.calendar import CalendarEvent
from app.models.event_outcome import EventOutcome
from app.services.calendar import ASTANA
from app.services.review_score import OUTCOMES, DayScore, summarize
from app.services.settings import get_setting, set_setting

# The evening review goes out at this Almaty time unless he moves it on the
# calendar page. Late enough that the day is over, early enough to stay awake.
REVIEW_TIME_KEY = "bot_review_time"
DEFAULT_REVIEW_TIME = "21:30"


def _now() -> str:
    return datetime.now(ASTANA).isoformat()


def events_of_day(db: Session, day: str) -> list[CalendarEvent]:
    """Every event whose local day is `day`, in clock order.

    starts_at is either "YYYY-MM-DD" (all-day) or an ISO datetime carrying the
    Almaty offset, so a prefix match is the local day in both shapes.
    """
    events = (
        db.query(CalendarEvent)
        .filter(CalendarEvent.starts_at.like(f"{day}%"))
        .order_by(CalendarEvent.starts_at.asc())
        .all()
    )
    # All-day entries sort first — they frame the day rather than sitting at
    # midnight inside it.
    return sorted(events, key=lambda e: (len(e.starts_at) > 10, e.starts_at))


def get_outcome(db: Session, event_id: str) -> EventOutcome | None:
    return db.query(EventOutcome).filter(EventOutcome.event_id == event_id).first()


def outcomes_for(db: Session, event_ids: Sequence[str]) -> dict[str, EventOutcome]:
    if not event_ids:
        return {}
    rows = db.query(EventOutcome).filter(EventOutcome.event_id.in_(list(event_ids))).all()
    return {row.event_id: row for row in rows}


def record_outcome(
    db: Session, event_id: str, outcome: str, note: str | None = None
) -> EventOutcome:
    """Answer, or re-answer. A note already attached survives a changed answer."""
    if outcome not in OUTCOMES:
        raise ValueError(f"Unknown outcome: {outcome}")

    row = get_outcome(db, event_id)
    if row:
        row.outcome = outcome
        if note is not None:
            row.note = note
        row.recorded_at = _now()
    else:
        row = EventOutcome(event_id=event_id, outcome=outcome, note=note, recorded_at=_now())
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def set_note(db: Session, event_id: str, note: str) -> EventOutcome | None:
    """Attach a note to an answer. Nothing answered = nothing to attach it to."""
    row = get_outcome(db, event_id)
    if not row:
        return None
    row.note = note.strip() or None
    row.recorded_at = _now()
    db.commit()
    db.refresh(row)
    return row


def delete_outcome(db: Session, event_id: str) -> None:
    """Called when the event itself goes, so a deleted day cannot haunt a score."""
    db.query(EventOutcome).filter(EventOutcome.event_id == event_id).delete()
    db.commit()


def day_score(db: Session, day: str) -> DayScore:
    events = events_of_day(db, day)
    recorded = outcomes_for(db, [e.id for e in events])
    answers = [recorded[e.id].outcome for e in events if e.id in recorded]
    return summarize(day, len(events), answers)


def day_scores(db: Session, days: Sequence[str]) -> list[DayScore]:
    return [day_score(db, day) for day in days]


# --- when the review goes out ---------------------------------------------


def normalize_time(value: str) -> str:
    """"9:5" → "09:05". Raises ValueError on anything that is not a clock time."""
    hour, _, minute = value.strip().partition(":")
    h, m = int(hour), int(minute)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError("Time must be between 00:00 and 23:59")
    return f"{h:02d}:{m:02d}"


def get_review_time(db: Session) -> str:
    stored = get_setting(db, REVIEW_TIME_KEY)
    if not stored:
        return DEFAULT_REVIEW_TIME
    try:
        return normalize_time(stored)
    except ValueError:
        return DEFAULT_REVIEW_TIME


def set_review_time(db: Session, value: str) -> str:
    normalized = normalize_time(value)
    set_setting(db, REVIEW_TIME_KEY, normalized)
    return normalized
