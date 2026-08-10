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


# The four states a book can be in. `abandoned` is the export's "could not
# finish" — worth keeping visible rather than deleting, since a shelved book is
# part of the reading history.
STATUSES = ("not_started", "in_progress", "completed", "abandoned")
