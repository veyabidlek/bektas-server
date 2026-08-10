"""The Quran reading log — the entries `islam_quran.py` sums into
`pages_logged`.

Its own module rather than a corner of the khatms service: the log is written
far more often than khatms are, and keeping the two apart is what stops either
file from turning into the "islam service".
"""

import uuid

from sqlalchemy.orm import Session

from app.models.islam import QuranLogEntry
from app.schemas.islam import QuranLogCreate, QuranLogEntryOut


def _out(entry: QuranLogEntry) -> QuranLogEntryOut:
    return QuranLogEntryOut(
        id=entry.id,
        khatm_id=entry.khatm_id,
        date=entry.date,
        page_from=entry.page_from,
        page_to=entry.page_to,
        note=entry.note,
    )


def out(entry: QuranLogEntry) -> QuranLogEntryOut:
    return _out(entry)


def list_entries(db: Session, khatm_id: str | None = None) -> list[QuranLogEntryOut]:
    """Newest date first. `id` breaks the tie, so two sittings logged on the
    same day still come back in a stable order."""
    query = db.query(QuranLogEntry)
    if khatm_id:
        query = query.filter(QuranLogEntry.khatm_id == khatm_id)
    entries = query.order_by(QuranLogEntry.date.desc(), QuranLogEntry.id.desc()).all()
    return [_out(e) for e in entries]


def add_entry(db: Session, data: QuranLogCreate) -> QuranLogEntry:
    entry = QuranLogEntry(
        id=uuid.uuid4().hex[:12],
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


def get_entry(db: Session, entry_id: str) -> QuranLogEntry | None:
    return db.query(QuranLogEntry).filter(QuranLogEntry.id == entry_id).first()


def delete_entry(db: Session, entry: QuranLogEntry) -> None:
    db.delete(entry)
    db.commit()
