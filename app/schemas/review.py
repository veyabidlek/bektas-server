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
    """When the bot writes, in Asia/Almaty. Both are "HH:MM".

    `review_time` is the nightly "how did today go?"; `weekly_digest_time` is
    the Sunday digest. They live in one payload because they are one idea to
    him — when the bot talks — and one request for the panel that edits them.
    """

    review_time: str
    weekly_digest_time: str


class ReviewSettingsIn(BaseModel):
    """A partial save: each field is edited on its own, so each arrives alone."""

    review_time: str | None = None
    weekly_digest_time: str | None = None
