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

    # Where the work is: "todo" | "in_progress" | "done" — the board's three
    # columns, and the only thing that decides whether a task is finished.
    status: Mapped[str] = mapped_column(String, nullable=False, default="todo", index=True)

    # ⚠️ `done` is a DENORMALIZED COPY of `status == "done"`, not a second
    # opinion. It exists because four queries across the bot, the weekly digest
    # and this service filter on it in SQL, and it is written **only** by
    # `services.tasks._apply_status`. Never assign to it anywhere else — the
    # moment two writers exist the board and the checkbox start disagreeing.
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # The completion date. Cleared when a task leaves "done", so "recently
    # completed" ordering can never show a stale timestamp for open work.
    done_at: Mapped[str | None] = mapped_column(String, nullable=True)

    # The Eisenhower matrix, as two independent questions. NULL means "never
    # asked" — see task_rules.UNSORTED for why that is not the same as False.
    urgent: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    important: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Out of sight, not gone: an archived task keeps its status, its dates and
    # its notes, and is simply absent from the default reads.
    archived_at: Mapped[str | None] = mapped_column(String, nullable=True)

    # Where the task came from — "web" today, "telegram" / "inbox" once those
    # phases land. Kept as a free string so a new source needs no migration.
    source: Mapped[str] = mapped_column(String, nullable=False, default="web")

    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
