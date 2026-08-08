from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Task(Base):
    """A thing to do.

    `due_at` is either a plain "YYYY-MM-DD" (due that day, no particular time)
    or a full ISO datetime carrying the Almaty offset — the same two shapes the
    calendar uses, so the two features can share a day column without
    translating between formats.
    """

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    due_at: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    done_at: Mapped[str | None] = mapped_column(String, nullable=True)

    # Where the task came from — "web" today, "telegram" / "inbox" once those
    # phases land. Kept as a free string so a new source needs no migration.
    source: Mapped[str] = mapped_column(String, nullable=False, default="web")

    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
