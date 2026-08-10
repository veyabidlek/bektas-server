"""Khatms and the Quran reading log.

`pages_logged` is the only interesting thing here. It is computed, never
stored, and it is computed for the *whole list* in one grouped query rather
than per khatm — the list page shows every khatm at once, and a per-row count
would be N+1 queries for a number that SQL can add up in one.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.islam import Khatm, QuranLogEntry
from app.schemas.islam import (
    KhatmCreate,
    KhatmOut,
    KhatmUpdate,
    QuranLogCreate,
    QuranLogEntryOut,
)
from app.services.calendar import ASTANA


def _now() -> str:
    return datetime.now(timezone.utc).astimezone(ASTANA).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _pages_by_khatm(db: Session, khatm_id: str | None = None) -> dict[str, int]:
    """Sum of the inclusive ranges, per khatm, in one query."""
    total = func.sum(QuranLogEntry.page_to - QuranLogEntry.page_from + 1)
    query = db.query(QuranLogEntry.khatm_id, total)
    if khatm_id is not None:
        query = query.filter(QuranLogEntry.khatm_id == khatm_id)
    return {row[0]: int(row[1] or 0) for row in query.group_by(QuranLogEntry.khatm_id).all()}


def _out(khatm: Khatm, pages_logged: int) -> KhatmOut:
    return KhatmOut(
        id=khatm.id,
        name=khatm.name,
        kind=khatm.kind,
        portion=khatm.portion,
        target_pages=khatm.target_pages,
        pages_logged=pages_logged,
        started_at=khatm.started_at,
        completed_at=khatm.completed_at,
    )


def out(db: Session, khatm: Khatm) -> KhatmOut:
    """One khatm, with its count — every response carries `pages_logged`."""
    return _out(khatm, _pages_by_khatm(db, khatm.id).get(khatm.id, 0))


def list_khatms(db: Session) -> list[KhatmOut]:
    """Active first, then newest first.

    `completed_at.isnot(None)` sorts False (0) before True (1), which puts the
    running khatms on top without relying on NULLS FIRST — SQLite has none.
    """
    khatms = (
        db.query(Khatm)
        .order_by(
            Khatm.completed_at.isnot(None),
            Khatm.started_at.desc(),
            Khatm.id.desc(),
        )
        .all()
    )
    pages = _pages_by_khatm(db)
    return [_out(k, pages.get(k.id, 0)) for k in khatms]


def get_khatm(db: Session, khatm_id: str) -> Khatm | None:
    return db.query(Khatm).filter(Khatm.id == khatm_id).first()


def create_khatm(db: Session, data: KhatmCreate) -> Khatm:
    khatm = Khatm(
        id=_new_id(),
        name=data.name,
        kind=data.kind,
        portion=data.portion,
        target_pages=data.target_pages,
        started_at=_now(),
        completed_at=None,
    )
    db.add(khatm)
    db.commit()
    db.refresh(khatm)
    return khatm


def update_khatm(db: Session, khatm: Khatm, data: KhatmUpdate) -> Khatm:
    """Partial: only the fields the client actually sent are written, so
    `{"completed_at": null}` re-opens a khatm while `{"name": "..."}` leaves
    its completion alone."""
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(khatm, field, value)
    db.commit()
    db.refresh(khatm)
    return khatm


def delete_khatm(db: Session, khatm: Khatm) -> None:
    """Takes its log with it — an orphaned entry counts towards nothing."""
    db.delete(khatm)
    db.commit()


# --- the log --------------------------------------------------------------


def _entry_out(entry: QuranLogEntry) -> QuranLogEntryOut:
    return QuranLogEntryOut(
        id=entry.id,
        khatm_id=entry.khatm_id,
        date=entry.date,
        page_from=entry.page_from,
        page_to=entry.page_to,
        note=entry.note,
    )


def entry_out(entry: QuranLogEntry) -> QuranLogEntryOut:
    return _entry_out(entry)


def list_log(db: Session, khatm_id: str | None = None) -> list[QuranLogEntryOut]:
    query = db.query(QuranLogEntry)
    if khatm_id:
        query = query.filter(QuranLogEntry.khatm_id == khatm_id)
    entries = query.order_by(QuranLogEntry.date.desc(), QuranLogEntry.id.desc()).all()
    return [_entry_out(e) for e in entries]


def add_log_entry(db: Session, data: QuranLogCreate) -> QuranLogEntry:
    entry = QuranLogEntry(
        id=_new_id(),
        khatm_id=data.khatm_id,
        date=data.date,
        page_from=data.page_from,
        page_to=data.page_to,
        note=data.note,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_log_entry(db: Session, entry_id: str) -> QuranLogEntry | None:
    return db.query(QuranLogEntry).filter(QuranLogEntry.id == entry_id).first()


def delete_log_entry(db: Session, entry: QuranLogEntry) -> None:
    db.delete(entry)
    db.commit()
