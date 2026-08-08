from pydantic import BaseModel


class CalendarEventOut(BaseModel):
    id: str
    title: str
    starts_at: str
    ends_at: str | None = None
    all_day: bool = False
    notes: str = ""
    reminder_minutes: int | None = None
    google_event_id: str | None = None
    created_at: str
    updated_at: str


class CalendarEventCreate(BaseModel):
    title: str
    starts_at: str
    ends_at: str | None = None
    all_day: bool = False
    notes: str = ""
    reminder_minutes: int | None = None


class CalendarEventUpdate(BaseModel):
    title: str | None = None
    starts_at: str | None = None
    ends_at: str | None = None
    all_day: bool | None = None
    notes: str | None = None
    reminder_minutes: int | None = None


class GoogleStatus(BaseModel):
    """Why three states and not a boolean: "no client id in the env" is a
    different problem from "configured but nobody has clicked Connect yet",
    and the admin UI has to tell them apart.
    """

    configured: bool
    connected: bool
    connected_at: str | None = None
    last_error: str | None = None
    redirect_uri: str
