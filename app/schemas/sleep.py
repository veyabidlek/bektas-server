"""Bodies and responses for sleep ingestion.

The response half follows the house rule — snake_case, camelCased by the
client's `transformKeys()`. The **request** half is deliberately the loosest in
this codebase: it is filled in by an Apple Shortcut that Bektas assembled by
tapping boxes on a phone, and the field names HealthKit hands to it are
`startDate` / `endDate` / `value`. Rejecting those on a spelling would mean
debugging a recipe with no console, so every plausible spelling is accepted and
the canonical one stays documented.
"""

from pydantic import AliasChoices, BaseModel, Field

from app.schemas.islam import iso_date


class SleepSegmentIn(BaseModel):
    """One Apple Health sample.

    `startDate` / `endDate` / `value` are what HealthKit calls these, and a
    Shortcut that passes a sample through untouched sends exactly that.
    """

    start: str = Field(validation_alias=AliasChoices("start", "startDate", "start_date"))
    end: str = Field(validation_alias=AliasChoices("end", "endDate", "end_date"))
    stage: str = Field(
        default="asleep",
        validation_alias=AliasChoices("stage", "value", "sleepStage", "sleep_stage"),
    )


class SleepIngestIn(BaseModel):
    """A morning's upload: the night's samples, and optionally which night.

    `date` overrides the computed one. It exists for a backfill of an old
    export, not for the daily run — the shortcut should send segments and let
    the wake-up morning decide, which is what makes a re-run idempotent.
    """

    segments: list[SleepSegmentIn] = Field(default_factory=list)
    date: str | None = None

    def night_date(self) -> str | None:
        return iso_date(self.date) if self.date else None


class SleepNightOut(BaseModel):
    """A stored night. `None` on a stage means it was never reported."""

    date: str
    in_bed_minutes: int | None = None
    asleep_minutes: int = 0
    deep_minutes: int | None = None
    rem_minutes: int | None = None
    core_minutes: int | None = None
    awake_minutes: int | None = None
    bedtime: str | None = None
    wake_time: str | None = None


class SleepListOut(BaseModel):
    """Wrapped, like every other list here — room for a total later."""

    nights: list[SleepNightOut]


class SleepIngestOut(SleepNightOut):
    """What was stored, plus the stage names this server did not recognize.

    The echo is the whole debugging surface for the shortcut: an unrecognized
    stage still *counts* (toward asleep), so without it a typo'd recipe would
    keep reporting plausible numbers forever.
    """

    unrecognized_stages: list[str] = Field(default_factory=list)
