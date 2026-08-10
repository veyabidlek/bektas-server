from pydantic import BaseModel


class HabitOut(BaseModel):
    id: str
    name: str
    emoji: str
    color: str
    archived: bool = False
    visibility: str = "public"
    #: "education" / "health" / "islam" / … — a free string, None when ungrouped.
    category: str | None = None
    completed_days: dict[str, bool]


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


class HabitStats(BaseModel):
    completed: int
    total: int
    current_streak: int
