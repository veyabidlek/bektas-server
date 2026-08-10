from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.reading import ReadingItem
from app.schemas.reading import ReadingItemIn, ReadingItemOut
from app.services import reading_covers as covers
from app.services.calendar import ASTANA


def _now() -> str:
    return datetime.now(timezone.utc).astimezone(ASTANA).isoformat()


def _out(item: ReadingItem) -> ReadingItemOut:
    return ReadingItemOut(
        id=item.id,
        title=item.title,
        author=item.author,
        category=item.category,
        status=item.status,
        pages=item.pages,
        score=item.score,
        started=item.started,
        completed=item.completed,
        created_at=item.created_at,
        description=item.description,
        # The public serving route, never a path on disk — and None when there
        # is no cover, so the client can tell "no picture" from "broken one".
        cover_url=f"/api/reading/covers/{item.id}" if item.cover_image else None,
    )


def out(item: ReadingItem) -> ReadingItemOut:
    return _out(item)


def list_reading_items(
    db: Session, include_not_started: bool = True
) -> list[ReadingItemOut]:
    """Most recently finished first, unfinished books after them.

    `completed.is_(None)` sorts False (0) before True (1), which is how NULLs
    are pushed to the end without relying on the backend's NULLS LAST support —
    SQLite has none. `id` breaks the final tie so an import that writes a whole
    shelf within the same second still has one stable order.

    `include_not_started=False` is the public view: the backlog is the owner's
    business (Bektas 2026-08-10 — "only in admin"); visitors see only books
    that have actually been touched.
    """
    query = db.query(ReadingItem)
    if not include_not_started:
        query = query.filter(ReadingItem.status != "not_started")
    items = (
        query.order_by(
            ReadingItem.completed.is_(None),
            ReadingItem.completed.desc(),
            ReadingItem.created_at.desc(),
            ReadingItem.id.desc(),
        )
        .all()
    )
    return [_out(i) for i in items]


def get_reading_item(db: Session, item_id: int) -> ReadingItem | None:
    return db.query(ReadingItem).filter(ReadingItem.id == item_id).first()


def create_reading_item(db: Session, data: ReadingItemIn) -> ReadingItem:
    item = ReadingItem(
        title=data.title,
        author=data.author,
        category=data.category,
        status=data.status,
        pages=data.pages,
        score=data.score,
        started=data.started,
        completed=data.completed,
        description=data.description,
        created_at=_now(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_reading_item(db: Session, item: ReadingItem, data: ReadingItemIn) -> ReadingItem:
    """A full update: every field in the body is written, including back to None.

    PUT replaces, so an omitted optional field clears rather than preserving —
    the client always sends the whole object.

    `cover_image` is the exception, and it is not one: the cover never travels
    in this body (it is a multipart upload on its own route), so there is
    nothing here to replace it *with*. Clearing it would mean every edit of a
    title silently threw the picture away.
    """
    item.title = data.title
    item.author = data.author
    item.category = data.category
    item.status = data.status
    item.pages = data.pages
    item.score = data.score
    item.started = data.started
    item.completed = data.completed
    item.description = data.description
    db.commit()
    db.refresh(item)
    return item


def delete_reading_item(db: Session, item: ReadingItem) -> None:
    """Notes and sessions cascade; the cover file has to be unlinked by hand —
    the ORM knows nothing about the volume."""
    covers.delete_cover(item.cover_image)
    db.delete(item)
    db.commit()


def set_cover(db: Session, item: ReadingItem, data: bytes, content_type: str) -> ReadingItem:
    """Replacing a cover takes the old file off the volume in the same breath,
    otherwise every re-upload leaves a stray behind forever."""
    filename = covers.save_cover(str(item.id), data, content_type)
    covers.delete_cover(item.cover_image)
    item.cover_image = filename
    db.commit()
    db.refresh(item)
    return item
