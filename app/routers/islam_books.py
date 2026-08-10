"""Islam books: the shelf, its covers, its notes and its sessions.

Admin-only, **covers included**. That is the diary's rule, not the portfolio's:
a project card is public content and its screenshot has to load for a logged-out
reader, but nothing in this section does. A browser cannot put an Authorization
header on an `<img>`, which is what the HttpOnly `bk_admin` cookie is for — it
rides along on the cover request and `require_admin` accepts it.
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.schemas.islam_media import (
    IslamBookCreate,
    IslamBookListOut,
    IslamBookNoteCreate,
    IslamBookNoteListOut,
    IslamBookNoteOut,
    IslamBookOut,
    IslamBookSessionCreate,
    IslamBookSessionListOut,
    IslamBookSessionOut,
    IslamBookUpdate,
)
from app.services import islam_book_logs as logs_svc
from app.services import islam_books as svc
from app.services import islam_covers as covers
from app.services.image_optimize import ALLOWED_CONTENT_TYPES

router = APIRouter(prefix="/api/islam/books", tags=["islam"])


def _book_or_404(db: Session, book_id: str):
    book = svc.get_book(db, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


# --- the shelf ------------------------------------------------------------


@router.get("", response_model=IslamBookListOut)
def list_books(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    return IslamBookListOut(items=svc.list_books(db))


@router.post("", response_model=IslamBookOut, status_code=201)
def create_book(
    data: IslamBookCreate, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    return svc.out(svc.create_book(db, data))


@router.patch("/{book_id}", response_model=IslamBookOut)
def update_book(
    book_id: str,
    data: IslamBookUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    return svc.out(svc.update_book(db, _book_or_404(db, book_id), data))


@router.delete("/{book_id}", status_code=204)
def delete_book(
    book_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    """Notes and sessions cascade; the cover file comes off the volume too."""
    svc.delete_book(db, _book_or_404(db, book_id))


# --- covers ---------------------------------------------------------------
# Declared before the note/session routes only for readability — `covers/{id}`
# and `{book_id}/...` cannot collide, they have different shapes.


@router.get("/covers/{book_id}")
def serve_book_cover(
    book_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    book = _book_or_404(db, book_id)
    if not book.cover_image:
        raise HTTPException(status_code=404, detail="No cover")

    path = covers.path_for(book.cover_image)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cover file missing")

    return FileResponse(
        path,
        media_type=covers.media_type(book.cover_image),
        # Private: his shelf is not for a shared cache to hold onto.
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.post("/{book_id}/cover", response_model=IslamBookOut)
async def upload_book_cover(
    book_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """One file, field `file`. Answers with the updated book so the client can
    swap the card in place without a second request."""
    book = _book_or_404(db, book_id)

    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415, detail=f"Unsupported image type: {content_type or 'unknown'}"
        )

    data = await file.read(covers.MAX_UPLOAD_BYTES + 1)
    if len(data) > covers.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"{file.filename} is too large")
    if not data:
        raise HTTPException(status_code=422, detail="No image uploaded")

    return svc.out(svc.set_cover(db, book, data, content_type))


# --- notes ----------------------------------------------------------------


@router.get("/{book_id}/notes", response_model=IslamBookNoteListOut)
def list_book_notes(
    book_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    _book_or_404(db, book_id)
    return IslamBookNoteListOut(items=logs_svc.list_notes(db, book_id))


@router.post("/{book_id}/notes", response_model=IslamBookNoteOut, status_code=201)
def add_book_note(
    book_id: str,
    data: IslamBookNoteCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    _book_or_404(db, book_id)
    return logs_svc.add_note(db, book_id, data)


@router.delete("/{book_id}/notes/{note_id}", status_code=204)
def delete_book_note(
    book_id: str,
    note_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if not logs_svc.delete_note(db, book_id, note_id):
        raise HTTPException(status_code=404, detail="Note not found")


# --- sessions -------------------------------------------------------------


@router.get("/{book_id}/sessions", response_model=IslamBookSessionListOut)
def list_book_sessions(
    book_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    _book_or_404(db, book_id)
    return IslamBookSessionListOut(items=logs_svc.list_sessions(db, book_id))


@router.post("/{book_id}/sessions", response_model=IslamBookSessionOut, status_code=201)
def add_book_session(
    book_id: str,
    data: IslamBookSessionCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    _book_or_404(db, book_id)
    return logs_svc.add_session(db, book_id, data)


@router.delete("/{book_id}/sessions/{session_id}", status_code=204)
def delete_book_session(
    book_id: str,
    session_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if not logs_svc.delete_session(db, book_id, session_id):
        raise HTTPException(status_code=404, detail="Session not found")
