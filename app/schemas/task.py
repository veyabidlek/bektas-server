from pydantic import BaseModel


class TaskOut(BaseModel):
    id: str
    title: str
    notes: str = ""
    due_at: str | None = None
    # True when the due date carries no particular time — the calendar puts
    # these in its all-day row.
    due_all_day: bool = False
    done: bool = False
    done_at: str | None = None
    source: str = "web"
    created_at: str
    updated_at: str


class TaskCreate(BaseModel):
    title: str
    notes: str = ""
    due_at: str | None = None
    source: str = "web"


class TaskUpdate(BaseModel):
    title: str | None = None
    notes: str | None = None
    # Explicit null clears the due date, which is why this is not just optional:
    # `exclude_unset` tells "not mentioned" apart from "set to nothing".
    due_at: str | None = None
    done: bool | None = None


class TaskDoneUpdate(BaseModel):
    """Omit `done` to toggle whatever it currently is."""

    done: bool | None = None


class TaskTodaySummary(BaseModel):
    """What the dashboard card needs in one request."""

    today: str
    overdue_count: int
    today_count: int
    tasks: list[TaskOut]
