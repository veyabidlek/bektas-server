from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EventOutcome(Base):
    """How a calendar event actually went.

    One row per event — the event id *is* the primary key, so answering again
    overwrites rather than piling up a history. "Did I get up at 07:00?" has
    one true answer per day, and the question is asked the same evening.

    An event with no row was simply never reviewed; that is a third state and
    deliberately not stored as an outcome value.
    """

    __tablename__ = "event_outcomes"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    # 'done' | 'partial' | 'no'.
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[str] = mapped_column(String, nullable=False)
