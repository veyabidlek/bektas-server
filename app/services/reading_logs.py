"""What he wrote and what he actually read — the two logs hanging off a book.

Separate from `reading.py` for the reason `islam_book_logs.py` is separate from
`islam_books.py`: these rows are written many times per shelf entry, and the
file that owns the shelf should not also own its history.

Both lists come back newest-date first, with `id` breaking the tie so two
sittings on the same day still have one stable order.
"""

from sqlalchemy.orm import Session

from app.models.reading import ReadingNote, ReadingSession
from app.schemas.reading import (
    ReadingNoteIn,
    ReadingNoteOut,
    ReadingSessionIn,
    ReadingSessionOut,
)

# --- notes ----------------------------------------------------------------


def _note_out(note: ReadingNote) -> ReadingNoteOut:
    return ReadingNoteOut(
        id=note.id,
        item_id=note.item_id,
        date=note.date,
        page_from=note.page_from,
        page_to=note.page_to,
        body_md=note.body_md,
    )


def list_notes(db: Session, item_id: int) -> list[ReadingNoteOut]:
    notes = (
        db.query(ReadingNote)
        .filter(ReadingNote.item_id == item_id)
        .order_by(ReadingNote.date.desc(), ReadingNote.id.desc())
        .all()
    )
    return [_note_out(n) for n in notes]


def add_note(db: Session, item_id: int, data: ReadingNoteIn) -> ReadingNoteOut:
    note = ReadingNote(
        item_id=item_id,
        date=data.date,
        page_from=data.page_from,
        page_to=data.page_to,
        body_md=data.body_md,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return _note_out(note)


def delete_note(db: Session, item_id: int, note_id: int) -> bool:
    """Scoped to the item on purpose: a note id from another book's URL must
    not delete anything, even though ids are unique on their own."""
    note = (
        db.query(ReadingNote)
        .filter(ReadingNote.id == note_id, ReadingNote.item_id == item_id)
        .first()
    )
    if not note:
        return False
    db.delete(note)
    db.commit()
    return True


# --- sessions -------------------------------------------------------------


def _session_out(session: ReadingSession) -> ReadingSessionOut:
    return ReadingSessionOut(
        id=session.id,
        item_id=session.item_id,
        date=session.date,
        pages=session.pages,
        minutes=session.minutes,
    )


def list_sessions(db: Session, item_id: int) -> list[ReadingSessionOut]:
    sessions = (
        db.query(ReadingSession)
        .filter(ReadingSession.item_id == item_id)
        .order_by(ReadingSession.date.desc(), ReadingSession.id.desc())
        .all()
    )
    return [_session_out(s) for s in sessions]


def add_session(db: Session, item_id: int, data: ReadingSessionIn) -> ReadingSessionOut:
    session = ReadingSession(
        item_id=item_id,
        date=data.date,
        pages=data.pages,
        minutes=data.minutes,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_out(session)


def delete_session(db: Session, item_id: int, session_id: int) -> bool:
    session = (
        db.query(ReadingSession)
        .filter(ReadingSession.id == session_id, ReadingSession.item_id == item_id)
        .first()
    )
    if not session:
        return False
    db.delete(session)
    db.commit()
    return True
