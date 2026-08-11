from typing import Literal

from pydantic import BaseModel

#: What one day in `completed_days` may be. `True` — not the string "done" — is
#: what a fully-done day serializes to, so every client written against the old
#: boolean map keeps working: it truthy-checks, and "partial" is truthy too.
#: A missed day is simply absent from the map.
DayState = Literal[True, "partial"]

#: What the writer may ask for. "none" exists only in the request — it means
#: "forget this day", and forgetting is stored as the absence of a row.
MarkState = Literal["done", "partial", "none"]


class HabitOut(BaseModel):
    id: str
    name: str
    emoji: str
    color: str
    archived: bool = False
    visibility: str = "public"
    #: "education" / "health" / "islam" / … — a free string, None when ungrouped.
    category: str | None = None
    #: "YYYY-MM-DD" the habit was added; None for habits that predate the
    #: column (the client shows their earliest completion instead).
    created_at: str | None = None
    completed_days: dict[str, DayState]


class HabitUpdate(BaseModel):
    """A partial edit. An omitted field is left alone; `category: ""` clears it.

    `model_dump(exclude_unset=True)` is what tells the two apart, the same way
    `TaskUpdate` does — so "no category given" and "no category, please" stay
    different requests.
    """

    name: str | None = None
    emoji: str | None = None
    color: str | None = None
    category: str | None = None


class HabitToggleResponse(BaseModel):
    date: str
    completed: bool


class HabitMarkResponse(BaseModel):
    """The state the day is in now — "none" when the day was cleared."""

    date: str
    state: MarkState


class HabitStats(BaseModel):
    completed: int
    total: int
    current_streak: int
