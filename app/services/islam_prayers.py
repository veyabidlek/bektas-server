"""The prayer grid.

Two rules shape everything here:

- **A mark is a row; no mark is no row.** Clearing both status and quality
  deletes the row rather than writing two NULLs, so "he has not filled this in
  yet" stays distinguishable from "he skipped it". A grid of booleans could
  never tell those apart, and the difference is the whole point of tracking.
- **The range read is dense.** Every day between `from` and `to` comes back,
  untouched days included as `entries: {}`, because the client renders a
  calendar and a gap in the array would shift every cell after it.
"""

from datetime import date as date_cls
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.islam import PrayerMark
from app.schemas.islam import PrayerDayOut, PrayerMarkIn, PrayerMarkOut

# A year and a leap day. Wider than any view the client draws, and a hard stop
# on a typo'd `from=1970-01-01` walking the whole epoch a day at a time.
MAX_RANGE_DAYS = 366


def is_valid_date(day: str) -> bool:
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def get_day(db: Session, day: str) -> PrayerDayOut:
    """The whole day — the shape every write answers with, so the client can
    replace one day wholesale instead of patching a cell into place."""
    marks = db.query(PrayerMark).filter(PrayerMark.date == day).all()
    return PrayerDayOut(
        date=day,
        entries={
            m.prayer: PrayerMarkOut(status=m.status, quality=m.quality) for m in marks
        },
    )


def set_mark(db: Session, day: str, prayer: str, data: PrayerMarkIn) -> PrayerDayOut:
    """Upsert one cell, or delete it when both fields come back empty."""
    mark = (
        db.query(PrayerMark)
        .filter(PrayerMark.date == day, PrayerMark.prayer == prayer)
        .first()
    )

    if data.status is None and data.quality is None:
        if mark:
            db.delete(mark)
            db.commit()
        return get_day(db, day)

    if mark:
        mark.status = data.status
        mark.quality = data.quality
    else:
        db.add(
            PrayerMark(date=day, prayer=prayer, status=data.status, quality=data.quality)
        )
    db.commit()
    return get_day(db, day)


def list_days(db: Session, start: str, end: str) -> list[PrayerDayOut]:
    """Every day in the range, in order, whether or not it was ever marked.

    One query for the marks, then the days are filled in from the dictionary —
    a query per day would be up to 366 round trips for a month view.
    """
    marks = (
        db.query(PrayerMark)
        .filter(PrayerMark.date >= start, PrayerMark.date <= end)
        .all()
    )

    by_day: dict[str, dict[str, PrayerMarkOut]] = {}
    for mark in marks:
        by_day.setdefault(mark.date, {})[mark.prayer] = PrayerMarkOut(
            status=mark.status, quality=mark.quality
        )

    first = date_cls.fromisoformat(start)
    last = date_cls.fromisoformat(end)
    days: list[PrayerDayOut] = []
    cursor = first
    while cursor <= last:
        iso = cursor.isoformat()
        days.append(PrayerDayOut(date=iso, entries=by_day.get(iso, {})))
        cursor += timedelta(days=1)
    return days


def range_length(start: str, end: str) -> int:
    """Inclusive span in days — 1 when both ends are the same date."""
    return (date_cls.fromisoformat(end) - date_cls.fromisoformat(start)).days + 1
