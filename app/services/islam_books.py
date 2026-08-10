"""The Islam shelf itself. Its notes and sessions live in `islam_book_logs.py`."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.islam_media import IslamBook
from app.schemas.islam_media import IslamBookCreate, IslamBookOut, IslamBookUpdate
from app.services import islam_covers as covers
from app.services.calendar import ASTANA


def _now() -> str:
    return datetime.now(timezone.utc).astimezone(ASTANA).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def out(book: IslamBook) -> IslamBookOut:
    return IslamBookOut(
        id=book.id,
        title=book.title,
        author=book.author,
        description=book.description,
        # The auth-checked route, never a path on disk — and None when there is
        # no cover, so the client can tell "no picture" from "broken picture".
        cover_url=f"/api/islam/books/covers/{book.id}" if book.cover_image else None,
        status=book.status,
        total_pages=book.total_pages,
        created_at=book.created_at,
    )


def list_books(db: Session) -> list[IslamBookOut]:
    books = (
        db.query(IslamBook)
        .order_by(IslamBook.created_at.desc(), IslamBook.id.desc())
        .all()
    )
    return [out(b) for b in books]


def get_book(db: Session, book_id: str) -> IslamBook | None:
    return db.query(IslamBook).filter(IslamBook.id == book_id).first()


def create_book(db: Session, data: IslamBookCreate) -> IslamBook:
    book = IslamBook(
        id=_new_id(),
        title=data.title,
        author=data.author,
        description=data.description,
        status=data.status,
        total_pages=data.total_pages,
        created_at=_now(),
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


def update_book(db: Session, book: IslamBook, data: IslamBookUpdate) -> IslamBook:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(book, field, value)
    db.commit()
    db.refresh(book)
    return book


def delete_book(db: Session, book: IslamBook) -> None:
    """Notes and sessions cascade; the cover file has to be unlinked by hand —
    the ORM knows nothing about the volume."""
    covers.delete_cover(book.cover_image)
    db.delete(book)
    db.commit()


def set_cover(db: Session, book: IslamBook, data: bytes, content_type: str) -> IslamBook:
    """Replacing a cover takes the old file off the volume in the same breath,
    otherwise every re-upload leaves a stray behind forever."""
    filename = covers.save_cover(book.id, data, content_type)
    covers.delete_cover(book.cover_image)
    book.cover_image = filename
    db.commit()
    db.refresh(book)
    return book
