from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CalendarEvent(Base):
    """A private calendar entry. Admin-only at every layer — there is no
    visibility column because nothing here is ever public.

    Times are stored as ISO 8601 strings *with* an offset (Asia/Almaty unless
    the caller says otherwise), so a naive read can never drift by five hours.
    """

    __tablename__ = "calendar_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    starts_at: Mapped[str] = mapped_column(String, nullable=False, index=True)
    ends_at: Mapped[str | None] = mapped_column(String, nullable=True)
    all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Minutes before the start that a reminder should fire. None = no reminder.
    reminder_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Set once the event has been mirrored into Google Calendar.
    google_event_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
