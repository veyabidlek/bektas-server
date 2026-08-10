"""What he wrote and what he actually read — the two logs hanging off a book.

Separate from `islam_books.py` for the reason the reading log is separate from
khatms: these rows are written many times per shelf entry, and the file that
owns the shelf should not also own its history.

Both lists come back newest-date first, with `id` breaking the tie so two
sittings on the same day still have one stable order.
"""

import uuid

from sqlalchemy.orm import Session

from app.models.islam_media import IslamBookNote, IslamBookSession
from app.schemas.islam_media import (
    IslamBookNoteCreate,
    IslamBookNoteOut,
    IslamBookSessionCreate,
    IslamBookSessionOut,
)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# --- notes ----------------------------------------------------------------


def _note_out(note: IslamBookNote) -> IslamBookNoteOut:
    return IslamBookNoteOut(
        id=note.id,
        book_id=note.book_id,
        date=note.date,
        page_from=note.page_from,
        page_to=note.page_to,
        body_md=note.body_md,
    )


def list_notes(db: Session, book_id: str) -> list[IslamBookNoteOut]:
    notes = (
        db.query(IslamBookNote)
        .filter(IslamBookNote.book_id == book_id)
        .order_by(IslamBookNote.date.desc(), IslamBookNote.id.desc())
        .all()
    )
    return [_note_out(n) for n in notes]


def add_note(db: Session, book_id: str, data: IslamBookNoteCreate) -> IslamBookNoteOut:
    note = IslamBookNote(
        id=_new_id(),
        book_id=book_id,
        date=data.date,
        page_from=data.page_from,
        page_to=data.page_to,
        body_md=data.body_md,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return _note_out(note)


def delete_note(db: Session, book_id: str, note_id: str) -> bool:
    """Scoped to the book on purpose: a note id from another book's URL must
    not delete anything, even though ids are unique on their own."""
    note = (
        db.query(IslamBookNote)
        .filter(IslamBookNote.id == note_id, IslamBookNote.book_id == book_id)
        .first()
    )
    if not note:
        return False
    db.delete(note)
    db.commit()
    return True


# --- sessions -------------------------------------------------------------


def _session_out(session: IslamBookSession) -> IslamBookSessionOut:
    return IslamBookSessionOut(
        id=session.id,
        book_id=session.book_id,
        date=session.date,
        pages=session.pages,
        minutes=session.minutes,
    )


def list_sessions(db: Session, book_id: str) -> list[IslamBookSessionOut]:
    sessions = (
        db.query(IslamBookSession)
        .filter(IslamBookSession.book_id == book_id)
        .order_by(IslamBookSession.date.desc(), IslamBookSession.id.desc())
        .all()
    )
    return [_session_out(s) for s in sessions]


def add_session(
    db: Session, book_id: str, data: IslamBookSessionCreate
) -> IslamBookSessionOut:
    session = IslamBookSession(
        id=_new_id(),
        book_id=book_id,
        date=data.date,
        pages=data.pages,
        minutes=data.minutes,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_out(session)


def delete_session(db: Session, book_id: str, session_id: str) -> bool:
    session = (
        db.query(IslamBookSession)
        .filter(IslamBookSession.id == session_id, IslamBookSession.book_id == book_id)
        .first()
    )
    if not session:
        return False
    db.delete(session)
    db.commit()
    return True
