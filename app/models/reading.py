from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ReadingItem(Base):
    """One book on the public reading list.

    Imported from a Notion database export (`scripts/import_reading.py`), and
    shaped to survive that: every column except the title is nullable, because
    a Notion table is half-filled by nature — a book that has only been *added*
    carries nothing but its name.

    `category` is the export's "Type" select, kept as a **free string** rather
    than an enum. The values in the data today are Novel / Self-Development /
    Spiritual / Programming / Psychology, and a sixth one must cost no
    migration — the same reasoning as `tasks.source`. `status` is the one
    closed set (`STATUSES`), because the client renders a different lane per
    value and an unknown one would have nowhere to go.

    Dates are ISO "YYYY-MM-DD" strings, as everywhere else in this codebase.
    The export's "Day Count" column is deliberately **not** stored: it is
    `completed - started`, and a derived number that can disagree with its own
    inputs is worse than no number. The client computes it.

    `description` and `cover_image` arrived with the public Shelf view
    (2026-08-10). The cover is a **filename** on the volume, the same split the
    Islam shelf uses — but served publicly, because /reading is a page anyone
    can look at.
    """

    __tablename__ = "reading_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    author: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="not_started")
    pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 1–5 stars, or nothing — an unrated book is the common case.
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started: Mapped[str | None] = mapped_column(String, nullable=True)
    completed: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    # What the shelf card says under the title. Long-form, so TEXT.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Filename on the volume, not bytes and not a URL. NULL = no cover yet.
    cover_image: Mapped[str | None] = mapped_column(String, nullable=True)
    # "public" / "friends" / "private", same vocabulary as articles and habits.
    # Defaults to private: the shelf was public until 2026-08-17 and is not any
    # more, so a new book is closed unless it is deliberately opened.
    visibility: Mapped[str] = mapped_column(String, nullable=False, default="private")

    notes: Mapped[list["ReadingNote"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["ReadingSession"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class ReadingNote(Base):
    """A thought while reading, optionally about a page range.

    Unlike the row it hangs off, this is **not** public: the shelf shows what
    he is reading, his notes on it are his own. Both logs are admin-only over
    the API.

    Integer ids, like `reading_items` — the Islam shelf's notes are strings
    because *its* books are. Matching the neighbouring table is what keeps a
    join readable.
    """

    __tablename__ = "reading_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("reading_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[str] = mapped_column(String, nullable=False, index=True)
    page_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    body_md: Mapped[str] = mapped_column(Text, nullable=False, default="")

    item: Mapped["ReadingItem"] = relationship(back_populates="notes")


class ReadingSession(Base):
    """A sitting with the book: how many pages, and how long if he timed it."""

    __tablename__ = "reading_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("reading_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[str] = mapped_column(String, nullable=False, index=True)
    pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    item: Mapped["ReadingItem"] = relationship(back_populates="sessions")


# The four states a book can be in. `abandoned` is the export's "could not
# finish" — worth keeping visible rather than deleting, since a shelved book is
# part of the reading history.
STATUSES = ("not_started", "in_progress", "completed", "abandoned")
