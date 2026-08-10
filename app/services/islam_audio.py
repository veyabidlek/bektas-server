"""The audio shelf — audiobooks and lecture playlists.

Mirrors `islam_books.py` down to the cover handling, which is why the file
handling itself lives in `islam_covers.py` and is called from both. What does
not mirror is the domain: audio has a `kind`, no page count, and its notes point
at a free-text position rather than a page range.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.islam_media import IslamAudio
from app.schemas.islam_media import IslamAudioCreate, IslamAudioOut, IslamAudioUpdate
from app.services import islam_covers as covers
from app.services.calendar import ASTANA


def _now() -> str:
    return datetime.now(timezone.utc).astimezone(ASTANA).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def out(audio: IslamAudio) -> IslamAudioOut:
    return IslamAudioOut(
        id=audio.id,
        title=audio.title,
        creator=audio.creator,
        description=audio.description,
        cover_url=f"/api/islam/audio/covers/{audio.id}" if audio.cover_image else None,
        kind=audio.kind,
        status=audio.status,
        created_at=audio.created_at,
    )


def list_audio(db: Session) -> list[IslamAudioOut]:
    items = (
        db.query(IslamAudio)
        .order_by(IslamAudio.created_at.desc(), IslamAudio.id.desc())
        .all()
    )
    return [out(a) for a in items]


def get_audio(db: Session, audio_id: str) -> IslamAudio | None:
    return db.query(IslamAudio).filter(IslamAudio.id == audio_id).first()


def create_audio(db: Session, data: IslamAudioCreate) -> IslamAudio:
    audio = IslamAudio(
        id=_new_id(),
        title=data.title,
        creator=data.creator,
        description=data.description,
        kind=data.kind,
        status=data.status,
        created_at=_now(),
    )
    db.add(audio)
    db.commit()
    db.refresh(audio)
    return audio


def update_audio(db: Session, audio: IslamAudio, data: IslamAudioUpdate) -> IslamAudio:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(audio, field, value)
    db.commit()
    db.refresh(audio)
    return audio


def delete_audio(db: Session, audio: IslamAudio) -> None:
    """Notes and sessions cascade; the cover file has to be unlinked by hand."""
    covers.delete_cover(audio.cover_image)
    db.delete(audio)
    db.commit()


def set_cover(db: Session, audio: IslamAudio, data: bytes, content_type: str) -> IslamAudio:
    filename = covers.save_cover(audio.id, data, content_type)
    covers.delete_cover(audio.cover_image)
    audio.cover_image = filename
    db.commit()
    db.refresh(audio)
    return audio
