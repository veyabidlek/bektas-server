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

    habit: Mapped["Habit"] = relationship(back_populates="completions")
