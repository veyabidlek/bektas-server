import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.diary import DiaryEntry, DiaryImage
from app.schemas.diary import DiaryEntryOut, DiaryEntrySummary, DiaryImageOut
from app.services.calendar import ASTANA
from app.services.image_optimize import dimensions, optimize_image

DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# On the named volume (bektas_data:/data), NOT in the image layer — writing
# inside the image means every `up --build` silently eats his photos.
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/data/uploads")) / "diary"

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
PREVIEW_CHARS = 140


def _now() -> str:
    return datetime.now(timezone.utc).astimezone(ASTANA).isoformat()


def today() -> str:
    """Today in Almaty — the day the diary opens on."""
    return datetime.now(timezone.utc).astimezone(ASTANA).strftime("%Y-%m-%d")


def is_valid_day(day: str) -> bool:
    if not DAY_RE.match(day):
        return False
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _preview(body_md: str) -> str:
    """First line-ish of the entry, with the markdown noise taken off."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body_md)  # images
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links → their text
    text = re.sub(r"[#>*_`~-]", "", text)
    text = " ".join(text.split())
    return text[:PREVIEW_CHARS]


def _image_out(image: DiaryImage) -> DiaryImageOut:
    return DiaryImageOut(
        id=image.id,
        day=image.day,
        width=image.width,
        height=image.height,
        created_at=image.created_at,
    )


def get_entry(db: Session, day: str) -> DiaryEntryOut:
    """Always returns a shell — an unwritten day is `exists: False`, not a 404,
    so the editor can open on any date."""
    entry = db.query(DiaryEntry).filter(DiaryEntry.day == day).first()
    if not entry:
        return DiaryEntryOut(day=day, title="", body_md="", exists=False, images=[])

    return DiaryEntryOut(
        day=entry.day,
        title=entry.title or "",
        body_md=entry.body_md,
        exists=True,
        images=[_image_out(i) for i in entry.images],
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def upsert_entry(db: Session, day: str, body_md: str, title: str = "") -> DiaryEntryOut:
    """Write the day. Same date twice = an edit, never a duplicate."""
    entry = db.query(DiaryEntry).filter(DiaryEntry.day == day).first()
    now = _now()
    clean_title = (title or "").strip()

    if entry:
        entry.title = clean_title
        entry.body_md = body_md
        entry.updated_at = now
    else:
        entry = DiaryEntry(
            day=day, title=clean_title, body_md=body_md, created_at=now, updated_at=now
        )
        db.add(entry)

    db.commit()
    return get_entry(db, day)


def ensure_entry(db: Session, day: str) -> DiaryEntry:
    """A photo can be attached before a word is written, so the row has to exist."""
    entry = db.query(DiaryEntry).filter(DiaryEntry.day == day).first()
    if not entry:
        now = _now()
        entry = DiaryEntry(day=day, title="", body_md="", created_at=now, updated_at=now)
        db.add(entry)
        db.commit()
        db.refresh(entry)
    return entry


def list_entries(db: Session, limit: int = 60, before: str | None = None) -> list[DiaryEntrySummary]:
    q = db.query(DiaryEntry)
    if before:
        q = q.filter(DiaryEntry.day < before)
    entries = q.order_by(DiaryEntry.day.desc()).limit(limit).all()

    return [
        DiaryEntrySummary(
            day=e.day,
            title=e.title or "",
            preview=_preview(e.body_md),
            image_count=len(e.images),
            updated_at=e.updated_at,
        )
        for e in entries
    ]


def delete_entry(db: Session, day: str) -> bool:
    entry = db.query(DiaryEntry).filter(DiaryEntry.day == day).first()
    if not entry:
        return False
    for image in list(entry.images):
        _unlink(image)
    db.delete(entry)
    db.commit()
    return True


# --- photos ---


def _path_for(image_id: str, filename: str) -> Path:
    return UPLOAD_DIR / filename if filename else UPLOAD_DIR / image_id


def _unlink(image: DiaryImage) -> None:
    try:
        _path_for(image.id, image.filename).unlink(missing_ok=True)
    except OSError:
        pass  # a missing file must not block deleting the row


def add_image(db: Session, day: str, data: bytes, content_type: str) -> DiaryImageOut:
    ensure_entry(db, day)

    body, out_type, ext = optimize_image(data, content_type)
    width, height = dimensions(body)

    image_id = uuid.uuid4().hex[:12]
    filename = f"{day}-{image_id}.{ext}"

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / filename).write_bytes(body)

    highest = (
        db.query(DiaryImage)
        .filter(DiaryImage.day == day)
        .order_by(DiaryImage.sort_order.desc())
        .first()
    )
    image = DiaryImage(
        id=image_id,
        day=day,
        filename=filename,
        content_type=out_type,
        width=width,
        height=height,
        size_bytes=len(body),
        sort_order=(highest.sort_order + 1) if highest else 0,
        created_at=_now(),
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return _image_out(image)


def get_image(db: Session, image_id: str) -> DiaryImage | None:
    return db.query(DiaryImage).filter(DiaryImage.id == image_id).first()


def image_path(image: DiaryImage) -> Path:
    return _path_for(image.id, image.filename)


def delete_image(db: Session, image_id: str) -> bool:
    image = get_image(db, image_id)
    if not image:
        return False
    _unlink(image)
    db.delete(image)
    db.commit()
    return True
