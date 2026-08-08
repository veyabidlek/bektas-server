import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.calendar import CalendarEvent
from app.schemas.calendar import CalendarEventCreate, CalendarEventOut, CalendarEventUpdate

# Every timestamp Bektas reads is Asia/Almaty (UTC+5) — same rule as the rest
# of the fleet. A datetime that arrives without an offset is *his* local time,
# so we attach Almaty rather than guessing UTC and being five hours wrong.
ASTANA = ZoneInfo("Asia/Almaty")


def normalize_dt(value: str) -> str:
    """ISO 8601 in, ISO 8601 with an explicit offset out."""
    text = value.strip()
    if not text:
        raise ValueError("Empty datetime")
    # A date on its own is an all-day marker; keep it as a plain date.
    if len(text) == 10 and text.count("-") == 2:
        datetime.strptime(text, "%Y-%m-%d")
        return text
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ASTANA)
    return parsed.isoformat()


def _now() -> str:
    return datetime.now(timezone.utc).astimezone(ASTANA).isoformat()


def _out(event: CalendarEvent) -> CalendarEventOut:
    return CalendarEventOut(
        id=event.id,
        title=event.title,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        all_day=event.all_day,
        notes=event.notes or "",
        reminder_minutes=event.reminder_minutes,
        google_event_id=event.google_event_id,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


def list_events(
    db: Session, start: str | None = None, end: str | None = None
) -> list[CalendarEventOut]:
    """Events in [start, end), or everything when unbounded.

    Timestamps are stored as ISO strings, which sort chronologically as text
    for any single offset — true here because everything is normalized to
    Asia/Almaty on the way in.
    """
    q = db.query(CalendarEvent)
    if start:
        q = q.filter(CalendarEvent.starts_at >= start)
    if end:
        q = q.filter(CalendarEvent.starts_at < end)
    return [_out(e) for e in q.order_by(CalendarEvent.starts_at.asc()).all()]


def all_events(db: Session) -> list[CalendarEvent]:
    """Every row, as ORM objects — for a full re-push to Google."""
    return db.query(CalendarEvent).order_by(CalendarEvent.starts_at.asc()).all()


def get_event(db: Session, event_id: str) -> CalendarEvent | None:
    return db.query(CalendarEvent).filter(CalendarEvent.id == event_id).first()


def create_event(db: Session, data: CalendarEventCreate) -> CalendarEvent:
    now = _now()
    event = CalendarEvent(
        id=str(uuid.uuid4())[:8],
        title=data.title.strip(),
        starts_at=normalize_dt(data.starts_at),
        ends_at=normalize_dt(data.ends_at) if data.ends_at else None,
        all_day=data.all_day,
        notes=(data.notes or "").strip(),
        reminder_minutes=data.reminder_minutes,
        created_at=now,
        updated_at=now,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def update_event(
    db: Session, event: CalendarEvent, data: CalendarEventUpdate
) -> CalendarEvent:
    fields = data.model_dump(exclude_unset=True)
    for field, value in fields.items():
        if field in ("starts_at", "ends_at") and value:
            value = normalize_dt(value)
        if field == "title" and isinstance(value, str):
            value = value.strip()
        setattr(event, field, value)
    event.updated_at = _now()
    db.commit()
    db.refresh(event)
    return event


def delete_event(db: Session, event: CalendarEvent) -> None:
    db.delete(event)
    db.commit()


def out(event: CalendarEvent) -> CalendarEventOut:
    return _out(event)
