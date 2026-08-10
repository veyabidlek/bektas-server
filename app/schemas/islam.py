"""Bodies and responses for the Quran half of the Islam section.

Responses are snake_case, as everywhere — the client's `transformKeys()`
camelCases them on arrival. **Requests** are the asymmetric part: the client's
`fetchApi` does not snake-case outgoing bodies, and the Islam calls in
`lib/api.ts` send `targetPages` / `khatmId` / `pageFrom` / `pageTo` /
`completedAt` as written. `either_case()` below makes every such field accept
both spellings, so the documented snake_case contract and the shipped client
are both correct rather than one of them being broken.
"""

from datetime import date as date_cls

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

from app.models.islam import (
    KHATM_KINDS,
    PRAYER_QUALITIES,
    PRAYER_STATUSES,
    QURAN_PAGES,
)


def either_case(name: str) -> AliasChoices:
    """Accept `page_from` and `pageFrom` for the same field.

    A superset of the contract, never a replacement for it: snake_case is what
    the API documents and what every other resource here takes.
    """
    head, *rest = name.split("_")
    return AliasChoices(name, head + "".join(part.capitalize() for part in rest))


def iso_date(value: str) -> str:
    """'YYYY-MM-DD' or a ValueError — the one date format in this codebase."""
    raw = (value or "").strip()
    try:
        return date_cls.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise ValueError(f"{raw!r} is not an ISO date (YYYY-MM-DD)") from exc


def blank_to_none(value: str | None) -> str | None:
    """A browser sends "" where the model means NULL."""
    if value is None:
        return None
    return value.strip() or None


# --- khatms ---------------------------------------------------------------


class KhatmOut(BaseModel):
    id: str
    name: str
    kind: str
    portion: str | None = None
    target_pages: int
    # Computed from the log on every read, never stored.
    pages_logged: int
    started_at: str
    completed_at: str | None = None


class KhatmListOut(BaseModel):
    items: list[KhatmOut]


class KhatmCreate(BaseModel):
    name: str
    kind: str = "individual"
    portion: str | None = None
    target_pages: int = Field(
        default=QURAN_PAGES, ge=1, validation_alias=either_case("target_pages")
    )

    @field_validator("name")
    @classmethod
    def _name_is_required(cls, v: str) -> str:
        name = (v or "").strip()
        if not name:
            raise ValueError("Name is required")
        return name

    @field_validator("kind")
    @classmethod
    def _kind_is_known(cls, v: str) -> str:
        kind = (v or "").strip() or "individual"
        if kind not in KHATM_KINDS:
            raise ValueError(f"kind must be one of {', '.join(KHATM_KINDS)}")
        return kind

    @field_validator("portion")
    @classmethod
    def _portion_blank_is_nothing(cls, v: str | None) -> str | None:
        return blank_to_none(v)


class KhatmUpdate(BaseModel):
    """Partial — read with `exclude_unset`, so an omitted field is untouched
    while an explicit `null` clears it (that is how a khatm is re-opened)."""

    name: str | None = None
    portion: str | None = None
    completed_at: str | None = Field(
        default=None, validation_alias=either_case("completed_at")
    )

    @field_validator("name")
    @classmethod
    def _name_stays_filled(cls, v: str | None) -> str | None:
        name = (v or "").strip()
        if not name:
            raise ValueError("Name is required")
        return name

    @field_validator("portion")
    @classmethod
    def _portion_blank_is_nothing(cls, v: str | None) -> str | None:
        return blank_to_none(v)


# --- the reading log ------------------------------------------------------


class QuranLogEntryOut(BaseModel):
    id: str
    khatm_id: str
    date: str
    page_from: int
    page_to: int
    note: str | None = None


class QuranLogListOut(BaseModel):
    items: list[QuranLogEntryOut]


class QuranLogCreate(BaseModel):
    khatm_id: str = Field(validation_alias=either_case("khatm_id"))
    date: str
    page_from: int = Field(ge=1, le=QURAN_PAGES, validation_alias=either_case("page_from"))
    page_to: int = Field(ge=1, le=QURAN_PAGES, validation_alias=either_case("page_to"))
    note: str | None = None

    @field_validator("date")
    @classmethod
    def _date_is_iso(cls, v: str) -> str:
        return iso_date(v)

    @field_validator("note")
    @classmethod
    def _note_blank_is_nothing(cls, v: str | None) -> str | None:
        return blank_to_none(v)

    @model_validator(mode="after")
    def _range_reads_forwards(self) -> "QuranLogCreate":
        if self.page_from > self.page_to:
            raise ValueError("page_from must not be greater than page_to")
        return self


# --- sura notes -----------------------------------------------------------


class SuraNoteOut(BaseModel):
    surah: int
    body_md: str
    updated_at: str


class SuraNoteListOut(BaseModel):
    items: list[SuraNoteOut]


class SuraNoteIn(BaseModel):
    body_md: str = Field(default="", validation_alias=either_case("body_md"))


# --- prayers --------------------------------------------------------------


class PrayerMarkIn(BaseModel):
    """Both fields null is the delete signal, not a validation error — that is
    how a mis-tapped cell is cleared."""

    status: str | None = None
    quality: str | None = None

    @field_validator("status")
    @classmethod
    def _status_is_known(cls, v: str | None) -> str | None:
        status = blank_to_none(v)
        if status is not None and status not in PRAYER_STATUSES:
            raise ValueError(f"status must be one of {', '.join(PRAYER_STATUSES)}")
        return status

    @field_validator("quality")
    @classmethod
    def _quality_is_known(cls, v: str | None) -> str | None:
        quality = blank_to_none(v)
        if quality is not None and quality not in PRAYER_QUALITIES:
            raise ValueError(f"quality must be one of {', '.join(PRAYER_QUALITIES)}")
        return quality


class PrayerMarkOut(BaseModel):
    status: str | None = None
    quality: str | None = None


class PrayerDayOut(BaseModel):
    """One day of the grid. `entries` holds only the prayers that carry a mark,
    so an untouched day is `{}` rather than seven nulls."""

    date: str
    entries: dict[str, PrayerMarkOut]


class PrayerRangeOut(BaseModel):
    days: list[PrayerDayOut]
