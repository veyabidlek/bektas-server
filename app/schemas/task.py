from pydantic import BaseModel


class TaskOut(BaseModel):
    id: str
    title: str
    notes: str = ""
    due_at: str | None = None
    # True when the due date carries no particular time — the calendar puts
    # these in its all-day row.
    due_all_day: bool = False

    # "todo" | "in_progress" | "done" — the board column this task is in.
    status: str = "todo"
    # ⚠️ Derived from `status`, kept because the calendar chip, the dashboard
    # card and the grouping util all read a boolean. It is not a second field
    # a client may set: send `status`.
    done: bool = False
    # When it was finished, cleared when it leaves Done. This IS the spec's
    # `completedAt` — one name for one value; a second alias would be one more
    # thing that can drift.
    done_at: str | None = None

    # The Eisenhower axes. `null` means the question has not been answered, so
    # a client must not coerce them to false — that is a different claim.
    urgent: bool | None = None
    important: bool | None = None
    # "do_first" | "schedule" | "delegate" | "eliminate" | "unsorted", computed
    # from the two above. Sent so every client draws the same quadrant.
    quadrant: str = "unsorted"

    archived_at: str | None = None

    source: str = "web"
    created_at: str
    updated_at: str


class TaskCreate(BaseModel):
    title: str
    notes: str = ""
    due_at: str | None = None
    status: str = "todo"
    urgent: bool | None = None
    important: bool | None = None
    source: str = "web"


class TaskUpdate(BaseModel):
    title: str | None = None
    notes: str | None = None
    # Explicit null clears the due date, which is why this is not just optional:
    # `exclude_unset` tells "not mentioned" apart from "set to nothing".
    due_at: str | None = None
    status: str | None = None
    # Same trick, and here it carries real meaning: null is "un-answer this
    # axis", which puts the task back in the matrix's unsorted tray.
    urgent: bool | None = None
    important: bool | None = None
    # Kept for the callers that predate `status`. Sending both is refused by
    # the router rather than silently resolved.
    done: bool | None = None


class TaskDoneUpdate(BaseModel):
    """Omit `done` to toggle whatever it currently is."""

    done: bool | None = None


class TaskStatusUpdate(BaseModel):
    """What a drag between board columns sends."""

    status: str


class TaskPriorityUpdate(BaseModel):
    """What dropping a card into an Eisenhower quadrant sends.

    Both axes every time. A quadrant is a point, not a nudge — sending one
    boolean and leaving the other as it was is how a card lands somewhere the
    user did not aim.
    """

    urgent: bool | None = None
    important: bool | None = None


class TaskArchiveUpdate(BaseModel):
    """Omit `archived` to toggle."""

    archived: bool | None = None


class TaskTodaySummary(BaseModel):
    """What the dashboard card needs in one request."""

    today: str
    overdue_count: int
    today_count: int
    tasks: list[TaskOut]
