from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Habit(Base):
    __tablename__ = "habits"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    emoji: Mapped[str] = mapped_column(String, nullable=False)
    color: Mapped[str] = mapped_column(String, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    visibility: Mapped[str] = mapped_column(String, nullable=False, default="public")
    # What the habit is *for* — "education", "health", "islam", … Kept a free
    # string, like `reading_items.category` and `tasks.source`: a new grouping
    # must cost no migration. NULL means ungrouped, which is the normal state.
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    # "YYYY-MM-DD" (Almaty) the habit was added. Nullable because rows that
    # predate the column have no recorded birthday — the client falls back to
    # the earliest completion, which is the honest "tracked since" for them.
    created_at: Mapped[str | None] = mapped_column(String, nullable=True)
    # Daily goal for counted habits (Quran = 2 pages/day). NULL is the plain
    # tick-off habit — the only kind that existed before the HabitKit import
    # (2026-08-11) — and 1 must mean exactly the same thing.
    target_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)

    completions: Mapped[list["HabitCompletion"]] = relationship(
        back_populates="habit",
        cascade="all, delete-orphan",
    )


class HabitCompletion(Base):
    __tablename__ = "habit_completions"
    __table_args__ = (
        UniqueConstraint("habit_id", "date", name="uq_habit_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    habit_id: Mapped[str] = mapped_column(
        String, ForeignKey("habits.id"), nullable=False
    )
    date: Mapped[str] = mapped_column(String, nullable=False)
    # How much of the habit was done that day: "done" or "partial". There is no
    # third value — a day that was missed has **no row**, which is what every
    # existing read already assumes. Defaulted to "done" so the old boolean
    # insert (`toggle_habit`, the seed) keeps meaning exactly what it meant.
    state: Mapped[str] = mapped_column(String, nullable=False, default="done")
    # The count behind a counted habit's day (1 of Quran's 2 pages). NULL on
    # plain habits and on state-only writes (TEZ, /toggle) — `state` stays the
    # value every read judges by; `amount` only explains it.
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)

    habit: Mapped["Habit"] = relationship(back_populates="completions")
