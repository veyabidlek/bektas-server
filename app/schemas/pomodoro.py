from pydantic import BaseModel, ConfigDict


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    color: str


class SessionCreate(BaseModel):
    project_id: str
    description: str
    duration_minutes: int


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    description: str
    started_at: str
    duration_minutes: int


class SessionStats(BaseModel):
    today_minutes: int
    today_sessions: int
    week_minutes: int
    week_sessions: int
    month_minutes: int
    month_sessions: int
    year_minutes: int
    year_sessions: int
    daily_minutes: dict[str, int]
