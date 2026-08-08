from pydantic import BaseModel


class DayScoreOut(BaseModel):
    """One day's effectiveness.

    `percent` is null for a day nothing was answered on — which the site shows
    as an empty bar rather than as a zero. A day nobody reviewed is not a bad
    day, it is an unknown one.
    """

    day: str
    total: int
    reviewed: int
    done: int
    partial: int
    no: int
    percent: int | None


class EventOutcomeOut(BaseModel):
    event_id: str
    outcome: str
    note: str | None = None
    recorded_at: str


class OutcomeIn(BaseModel):
    outcome: str
    note: str | None = None


class ReviewSummary(BaseModel):
    """What the dashboard chip and the 7-day strip need, in one request."""

    today: DayScoreOut
    yesterday: DayScoreOut
    days: list[DayScoreOut]


class ReviewSettings(BaseModel):
    """"HH:MM" in Asia/Almaty — when the bot asks how the day went."""

    review_time: str
