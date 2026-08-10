"""Islam audio: audiobooks and lecture playlists, with the same shapes the
books use — and the same posture. Admin-only everywhere, covers included.
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.schemas.islam_media import (
    IslamAudioCreate,
    IslamAudioListOut,
    IslamAudioNoteCreate,
    IslamAudioNoteListOut,
    IslamAudioNoteOut,
    IslamAudioOut,
    IslamAudioSessionCreate,
    IslamAudioSessionListOut,
    IslamAudioSessionOut,
    IslamAudioUpdate,
)
from app.services import islam_audio as svc
from app.services import islam_audio_logs as logs_svc
from app.services import islam_covers as covers
from app.services.image_optimize import ALLOWED_CONTENT_TYPES

router = APIRouter(prefix="/api/islam/audio", tags=["islam"])


def _audio_or_404(db: Session, audio_id: str):
    audio = svc.get_audio(db, audio_id)
    if not audio:
        raise HTTPException(status_code=404, detail="Audio not found")
    return audio


# --- the shelf ------------------------------------------------------------


@router.get("", response_model=IslamAudioListOut)
def list_audio(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    return IslamAudioListOut(items=svc.list_audio(db))


@router.post("", response_model=IslamAudioOut, status_code=201)
def create_audio(
    data: IslamAudioCreate, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    return svc.out(svc.create_audio(db, data))


@router.patch("/{audio_id}", response_model=IslamAudioOut)
def update_audio(
    audio_id: str,
    data: IslamAudioUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    return svc.out(svc.update_audio(db, _audio_or_404(db, audio_id), data))


@router.delete("/{audio_id}", status_code=204)
def delete_audio(
    audio_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    svc.delete_audio(db, _audio_or_404(db, audio_id))


# --- covers ---------------------------------------------------------------


@router.get("/covers/{audio_id}")
def serve_audio_cover(
    audio_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    audio = _audio_or_404(db, audio_id)
    if not audio.cover_image:
        raise HTTPException(status_code=404, detail="No cover")

    path = covers.path_for(audio.cover_image)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cover file missing")

    return FileResponse(
        path,
        media_type=covers.media_type(audio.cover_image),
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.post("/{audio_id}/cover", response_model=IslamAudioOut)
async def upload_audio_cover(
    audio_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    audio = _audio_or_404(db, audio_id)

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

    return svc.out(svc.set_cover(db, audio, data, content_type))


# --- notes ----------------------------------------------------------------


@router.get("/{audio_id}/notes", response_model=IslamAudioNoteListOut)
def list_audio_notes(
    audio_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    _audio_or_404(db, audio_id)
    return IslamAudioNoteListOut(items=logs_svc.list_notes(db, audio_id))


@router.post("/{audio_id}/notes", response_model=IslamAudioNoteOut, status_code=201)
def add_audio_note(
    audio_id: str,
    data: IslamAudioNoteCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    _audio_or_404(db, audio_id)
    return logs_svc.add_note(db, audio_id, data)


@router.delete("/{audio_id}/notes/{note_id}", status_code=204)
def delete_audio_note(
    audio_id: str,
    note_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if not logs_svc.delete_note(db, audio_id, note_id):
        raise HTTPException(status_code=404, detail="Note not found")


# --- sessions -------------------------------------------------------------


@router.get("/{audio_id}/sessions", response_model=IslamAudioSessionListOut)
def list_audio_sessions(
    audio_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    _audio_or_404(db, audio_id)
    return IslamAudioSessionListOut(items=logs_svc.list_sessions(db, audio_id))


@router.post("/{audio_id}/sessions", response_model=IslamAudioSessionOut, status_code=201)
def add_audio_session(
    audio_id: str,
    data: IslamAudioSessionCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    _audio_or_404(db, audio_id)
    return logs_svc.add_session(db, audio_id, data)


@router.delete("/{audio_id}/sessions/{session_id}", status_code=204)
def delete_audio_session(
    audio_id: str,
    session_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if not logs_svc.delete_session(db, audio_id, session_id):
        raise HTTPException(status_code=404, detail="Session not found")
