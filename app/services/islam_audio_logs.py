"""Notes and listening sessions hanging off an audio item.

The books' twin (`islam_book_logs.py`), differing only where the domain does:
a note carries a free-text `position` instead of a page range, and a session
counts minutes only — there are no pages to count.
"""

import uuid

from sqlalchemy.orm import Session

from app.models.islam_media import IslamAudioNote, IslamAudioSession
from app.schemas.islam_media import (
    IslamAudioNoteCreate,
    IslamAudioNoteOut,
    IslamAudioSessionCreate,
    IslamAudioSessionOut,
)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# --- notes ----------------------------------------------------------------


def _note_out(note: IslamAudioNote) -> IslamAudioNoteOut:
    return IslamAudioNoteOut(
        id=note.id,
        audio_id=note.audio_id,
        date=note.date,
        position=note.position,
        body_md=note.body_md,
    )


def list_notes(db: Session, audio_id: str) -> list[IslamAudioNoteOut]:
    notes = (
        db.query(IslamAudioNote)
        .filter(IslamAudioNote.audio_id == audio_id)
        .order_by(IslamAudioNote.date.desc(), IslamAudioNote.id.desc())
        .all()
    )
    return [_note_out(n) for n in notes]


def add_note(db: Session, audio_id: str, data: IslamAudioNoteCreate) -> IslamAudioNoteOut:
    note = IslamAudioNote(
        id=_new_id(),
        audio_id=audio_id,
        date=data.date,
        position=data.position,
        body_md=data.body_md,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return _note_out(note)


def delete_note(db: Session, audio_id: str, note_id: str) -> bool:
    """Scoped to its audio item, like the books' — an id from another item's
    URL must not delete anything."""
    note = (
        db.query(IslamAudioNote)
        .filter(IslamAudioNote.id == note_id, IslamAudioNote.audio_id == audio_id)
        .first()
    )
    if not note:
        return False
    db.delete(note)
    db.commit()
    return True


# --- sessions -------------------------------------------------------------


def _session_out(session: IslamAudioSession) -> IslamAudioSessionOut:
    return IslamAudioSessionOut(
        id=session.id,
        audio_id=session.audio_id,
        date=session.date,
        minutes=session.minutes,
    )


def list_sessions(db: Session, audio_id: str) -> list[IslamAudioSessionOut]:
    sessions = (
        db.query(IslamAudioSession)
        .filter(IslamAudioSession.audio_id == audio_id)
        .order_by(IslamAudioSession.date.desc(), IslamAudioSession.id.desc())
        .all()
    )
    return [_session_out(s) for s in sessions]


def add_session(
    db: Session, audio_id: str, data: IslamAudioSessionCreate
) -> IslamAudioSessionOut:
    session = IslamAudioSession(
        id=_new_id(), audio_id=audio_id, date=data.date, minutes=data.minutes
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_out(session)


def delete_session(db: Session, audio_id: str, session_id: str) -> bool:
    session = (
        db.query(IslamAudioSession)
        .filter(
            IslamAudioSession.id == session_id, IslamAudioSession.audio_id == audio_id
        )
        .first()
    )
    if not session:
        return False
    db.delete(session)
    db.commit()
    return True
