from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Habit(Base):
    __tablename__ = "habits"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    emoji: Mapped[str] = mapped_column(String, nullable=False)
    color: Mapped[str] = mapped_column(String, nullable=False)

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
