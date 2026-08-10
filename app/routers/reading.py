from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin, viewer_level
from app.schemas.reading import (
    ReadingItemIn,
    ReadingItemOut,
    ReadingListOut,
    ReadingNoteIn,
    ReadingNoteListOut,
    ReadingNoteOut,
    ReadingSessionIn,
    ReadingSessionListOut,
    ReadingSessionOut,
)
from app.services import reading as svc
from app.services import reading_covers as covers
from app.services import reading_logs as logs_svc
from app.services.image_optimize import ALLOWED_CONTENT_TYPES

# Reads are public — the reading list is a page anyone can look at, covers
# included: that is the portfolio's exception, not the diary's rule. The one
# gate: the not-started backlog is the owner's business and shows only to the
# admin ("only in admin", 2026-08-10). Writes are admin-only.
router = APIRouter(prefix="/api/reading", tags=["reading"])


def _item_or_404(db: Session, item_id: int):
    item = svc.get_reading_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Reading item not found")
    return item


@router.get("", response_model=ReadingListOut)
def list_reading(db: Session = Depends(get_db), level: str = Depends(viewer_level)):
    """Public, but the not-started backlog is admin-only."""
    return ReadingListOut(
        items=svc.list_reading_items(db, include_not_started=level == "admin")
    )


@router.post("", response_model=ReadingItemOut, status_code=201)
def create_reading_item(
    data: ReadingItemIn,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    return svc.out(svc.create_reading_item(db, data))


# --- covers ---------------------------------------------------------------
# Declared **before** every `/{item_id}` route on purpose. `covers` sits where
# an item id goes, and the ids here are ints, so the day someone adds a
# `GET /{item_id}` above this block, `/api/reading/covers/7` starts matching it
# with item_id="covers" and answering 422 — on a page that has no login to
# explain it. Order is the whole guarantee; keep this block where it is.


@router.get("/covers/{item_id}")
def serve_reading_cover(item_id: int, db: Session = Depends(get_db)):
    """Public, no auth dependency — the shelf is a page anyone can look at, so
    its covers have to load for a logged-out visitor."""
    item = _item_or_404(db, item_id)
    if not item.cover_image:
        raise HTTPException(status_code=404, detail="No cover")

    path = covers.path_for(item.cover_image)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cover file missing")

    return FileResponse(
        path,
        media_type=covers.media_type(item.cover_image),
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.post("/{item_id}/cover", response_model=ReadingItemOut)
async def upload_reading_cover(
    item_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """One file, field `file`. Answers with the updated item so the client can
    swap the card in place without a second request."""
    item = _item_or_404(db, item_id)

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

    return svc.out(svc.set_cover(db, item, data, content_type))


# --- the item -------------------------------------------------------------


@router.put("/{item_id}", response_model=ReadingItemOut)
def update_reading_item(
    item_id: int,
    data: ReadingItemIn,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    return svc.out(svc.update_reading_item(db, _item_or_404(db, item_id), data))


@router.delete("/{item_id}", status_code=204)
def delete_reading_item(
    item_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Notes and sessions cascade; the cover file comes off the volume too."""
    svc.delete_reading_item(db, _item_or_404(db, item_id))


# --- notes ----------------------------------------------------------------
# Admin-only, every one of them — unlike the shelf they hang off. What he is
# reading is public; what he wrote about it is not.


@router.get("/{item_id}/notes", response_model=ReadingNoteListOut)
def list_reading_notes(
    item_id: int, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    _item_or_404(db, item_id)
    return ReadingNoteListOut(items=logs_svc.list_notes(db, item_id))


@router.post("/{item_id}/notes", response_model=ReadingNoteOut, status_code=201)
def add_reading_note(
    item_id: int,
    data: ReadingNoteIn,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    _item_or_404(db, item_id)
    return logs_svc.add_note(db, item_id, data)


@router.delete("/{item_id}/notes/{note_id}", status_code=204)
def delete_reading_note(
    item_id: int,
    note_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if not logs_svc.delete_note(db, item_id, note_id):
        raise HTTPException(status_code=404, detail="Note not found")


# --- sessions -------------------------------------------------------------


@router.get("/{item_id}/sessions", response_model=ReadingSessionListOut)
def list_reading_sessions(
    item_id: int, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    _item_or_404(db, item_id)
    return ReadingSessionListOut(items=logs_svc.list_sessions(db, item_id))


@router.post("/{item_id}/sessions", response_model=ReadingSessionOut, status_code=201)
def add_reading_session(
    item_id: int,
    data: ReadingSessionIn,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    _item_or_404(db, item_id)
    return logs_svc.add_session(db, item_id, data)


@router.delete("/{item_id}/sessions/{session_id}", status_code=204)
def delete_reading_session(
    item_id: int,
    session_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if not logs_svc.delete_session(db, item_id, session_id):
        raise HTTPException(status_code=404, detail="Session not found")
