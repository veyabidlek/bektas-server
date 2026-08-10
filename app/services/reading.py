from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.reading import ReadingItem
from app.schemas.reading import ReadingItemIn, ReadingItemOut
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
    )


def out(item: ReadingItem) -> ReadingItemOut:
    return _out(item)


def list_reading_items(db: Session) -> list[ReadingItemOut]:
    """Most recently finished first, unfinished books after them.

    `completed.is_(None)` sorts False (0) before True (1), which is how NULLs
    are pushed to the end without relying on the backend's NULLS LAST support —
    SQLite has none. `id` breaks the final tie so an import that writes a whole
    shelf within the same second still has one stable order.
    """
    items = (
        db.query(ReadingItem)
        .order_by(
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
    """
    item.title = data.title
    item.author = data.author
    item.category = data.category
    item.status = data.status
    item.pages = data.pages
    item.score = data.score
    item.started = data.started
    item.completed = data.completed
    db.commit()
    db.refresh(item)
    return item


def delete_reading_item(db: Session, item: ReadingItem) -> None:
    db.delete(item)
    db.commit()
