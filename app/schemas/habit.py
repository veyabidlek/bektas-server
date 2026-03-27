from pydantic import BaseModel


class HabitOut(BaseModel):
    id: str
    name: str
    emoji: str
    color: str
    archived: bool = False
    completed_days: dict[str, bool]


class HabitToggleResponse(BaseModel):
    date: str
    completed: bool


class HabitStats(BaseModel):
    completed: int
    total: int
    current_streak: int
