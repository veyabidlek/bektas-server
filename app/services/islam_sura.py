"""Sura notes — one per surah, upserted.

Its own module rather than a corner of `islam_quran.py`: the surah number is
the identity, there is no create/update distinction, and none of the khatm
machinery applies. (Also the 150-line rule.)
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.islam import SuraNote
from app.schemas.islam import SuraNoteOut
from app.services.calendar import ASTANA

# The mushaf has 114 surahs; anything else is a client bug, answered 422.
FIRST_SURAH = 1
LAST_SURAH = 114


def _now() -> str:
    return datetime.now(timezone.utc).astimezone(ASTANA).isoformat()


def _out(note: SuraNote) -> SuraNoteOut:
    return SuraNoteOut(surah=note.surah, body_md=note.body_md, updated_at=note.updated_at)


def is_valid_surah(surah: int) -> bool:
    return FIRST_SURAH <= surah <= LAST_SURAH


def list_notes(db: Session) -> list[SuraNoteOut]:
    """In mushaf order — the order he reads them in, not the order he wrote."""
    notes = db.query(SuraNote).order_by(SuraNote.surah).all()
    return [_out(n) for n in notes]


def upsert_note(db: Session, surah: int, body_md: str) -> SuraNoteOut:
    """Writing about the same surah twice edits that note, never duplicates it —
    the diary's rule, with the surah number playing the part of the day."""
    note = db.query(SuraNote).filter(SuraNote.surah == surah).first()
    if note:
        note.body_md = body_md
    else:
        note = SuraNote(surah=surah, body_md=body_md, updated_at=_now())
        db.add(note)
    note.updated_at = _now()
    db.commit()
    db.refresh(note)
    return _out(note)


def delete_note(db: Session, surah: int) -> bool:
    note = db.query(SuraNote).filter(SuraNote.surah == surah).first()
    if not note:
        return False
    db.delete(note)
    db.commit()
    return True
