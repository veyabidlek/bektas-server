"""Sleep nights: reading the samples in, and reading the nights back out.

The DB half. All the arithmetic — parsing, stage names, overlap merging, which
morning a night belongs to — is the pure `sleep_night.py`, the same split
`assistant.py` / `assistant_format.py` and `weekly.py` / `week_stats.py` use.
Nothing here decides anything about sleep; it stores what that module computed.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.sleep import SleepNight
from app.schemas.sleep import SleepIngestIn, SleepNightOut
from app.services import sleep_night as night_svc
from app.services.calendar import ASTANA

#: The hard ceiling on `GET ?days=`. A year of nights is a chart; more is a
#: mistake in a URL.
MAX_DAYS = 366
DEFAULT_DAYS = 14


def _now() -> str:
    return datetime.now(timezone.utc).astimezone(ASTANA).isoformat()


def _out(row: SleepNight) -> SleepNightOut:
    return SleepNightOut(
        date=row.date,
        in_bed_minutes=row.in_bed_minutes,
        asleep_minutes=row.asleep_minutes,
        deep_minutes=row.deep_minutes,
        rem_minutes=row.rem_minutes,
        core_minutes=row.core_minutes,
        awake_minutes=row.awake_minutes,
        bedtime=row.bedtime,
        wake_time=row.wake_time,
    )


def out(row: SleepNight) -> SleepNightOut:
    return _out(row)


def parse_segments(data: SleepIngestIn) -> tuple[list[night_svc.Segment], list[str], list[dict]]:
    """The samples, the stage names that were not recognized, and what to store.

    A timestamp that cannot be read raises `ValueError` naming it — the router
    turns that into a 422, which is the only error message the shortcut's
    author will ever see. Unrecognized stages do **not** raise: they are
    counted as sleep and reported back, because a night that arrived is worth
    more than a night rejected on a spelling.
    """
    segments: list[night_svc.Segment] = []
    unrecognized: list[str] = []
    raw: list[dict] = []

    for item in data.segments:
        start = night_svc.parse_dt(item.start)
        end = night_svc.parse_dt(item.end)
        stage, known = night_svc.normalize_stage(item.stage)
        if not known and item.stage not in unrecognized:
            unrecognized.append(item.stage)
        segments.append(night_svc.Segment(start=start, end=end, stage=stage))
        # Both spellings are kept: the canonical one is what the aggregates were
        # computed from, the original is what the shortcut actually sent.
        raw.append(
            {
                "start": start.astimezone(ASTANA).isoformat(),
                "end": end.astimezone(ASTANA).isoformat(),
                "stage": stage,
                "raw_stage": item.stage,
            }
        )

    return segments, unrecognized, raw


def upsert_night(db: Session, night: night_svc.Night, segments: list[dict]) -> SleepNight:
    """Write the night, replacing whatever was filed under that date.

    The shortcut is allowed to run twice — a re-run must land on the same row,
    or a phone with a flaky morning would double-count the week.
    """
    row = db.query(SleepNight).filter(SleepNight.date == night.date).first()
    now = _now()
    if row is None:
        row = SleepNight(date=night.date, created_at=now)
        db.add(row)

    row.in_bed_minutes = night.in_bed_minutes
    row.asleep_minutes = night.asleep_minutes
    row.deep_minutes = night.deep_minutes
    row.rem_minutes = night.rem_minutes
    row.core_minutes = night.core_minutes
    row.awake_minutes = night.awake_minutes
    row.bedtime = night.bedtime
    row.wake_time = night.wake_time
    row.segments = segments
    row.updated_at = now

    db.commit()
    db.refresh(row)
    return row


def ingest(db: Session, data: SleepIngestIn) -> tuple[SleepNightOut | None, list[str]]:
    """A morning's upload, stored. `None` when nothing usable came in."""
    segments, unrecognized, raw = parse_segments(data)
    night = night_svc.aggregate(segments, data.night_date())
    if night is None:
        return None, unrecognized

    return _out(upsert_night(db, night, raw)), unrecognized


def list_nights(db: Session, days: int = DEFAULT_DAYS) -> list[SleepNightOut]:
    """The most recent `days` nights, newest first.

    A count of *nights*, not a calendar window: a band left on the charger for
    a week should shorten the chart, not blank it. Dates are "YYYY-MM-DD", so
    the text sort is the chronological one.
    """
    limit = max(1, min(days, MAX_DAYS))
    rows = db.query(SleepNight).order_by(SleepNight.date.desc()).limit(limit).all()
    return [_out(r) for r in rows]
