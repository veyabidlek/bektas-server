"""Bodies and responses for the books and audio he keeps under Islam.

The two mirror each other everywhere they can and diverge only where the
domains do: a book note carries a page range, an audio note a free position;
a book session counts pages, an audio session minutes.
"""

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.islam_media import AUDIO_KINDS, MEDIA_STATUSES
from app.schemas.islam import blank_to_none, either_case, iso_date


def _validated_status(v: str) -> str:
    status = (v or "").strip() or "reading"
    if status not in MEDIA_STATUSES:
        raise ValueError(f"status must be one of {', '.join(MEDIA_STATUSES)}")
    return status


def _required_title(v: str) -> str:
    title = (v or "").strip()
    if not title:
        raise ValueError("Title is required")
    return title


# --- books ----------------------------------------------------------------


class IslamBookOut(BaseModel):
    id: str
    title: str
    author: str | None = None
    description: str | None = None
    # The auth-checked route, or nothing. Never a path on disk.
    cover_url: str | None = None
    status: str
    total_pages: int | None = None
    created_at: str


class IslamBookListOut(BaseModel):
    items: list[IslamBookOut]


class IslamBookCreate(BaseModel):
    title: str
    author: str | None = None
    description: str | None = None
    status: str = "reading"
    total_pages: int | None = Field(
        default=None, ge=1, validation_alias=either_case("total_pages")
    )

    _title = field_validator("title")(_required_title)
    _status = field_validator("status")(_validated_status)
    _blanks = field_validator("author", "description")(blank_to_none)


class IslamBookUpdate(BaseModel):
    """Partial — read with `exclude_unset`, so an omitted field is untouched."""

    title: str | None = None
    author: str | None = None
    description: str | None = None
    status: str | None = None
    total_pages: int | None = Field(
        default=None, ge=1, validation_alias=either_case("total_pages")
    )

    _title = field_validator("title")(_required_title)
    _status = field_validator("status")(_validated_status)
    _blanks = field_validator("author", "description")(blank_to_none)


class IslamBookNoteOut(BaseModel):
    id: str
    book_id: str
    date: str
    page_from: int | None = None
    page_to: int | None = None
    body_md: str


class IslamBookNoteListOut(BaseModel):
    items: list[IslamBookNoteOut]


class IslamBookNoteCreate(BaseModel):
    date: str
    page_from: int | None = Field(
        default=None, ge=1, validation_alias=either_case("page_from")
    )
    page_to: int | None = Field(default=None, ge=1, validation_alias=either_case("page_to"))
    body_md: str = Field(default="", validation_alias=either_case("body_md"))

    _date = field_validator("date")(iso_date)

    @model_validator(mode="after")
    def _range_reads_forwards(self) -> "IslamBookNoteCreate":
        """Only when both ends are given — one-sided ranges are legitimate
        ("from page 12 onwards") and open-ended notes are the common case."""
        if self.page_from is not None and self.page_to is not None:
            if self.page_from > self.page_to:
                raise ValueError("page_from must not be greater than page_to")
        return self


class IslamBookSessionOut(BaseModel):
    id: str
    book_id: str
    date: str
    pages: int
    minutes: int | None = None


class IslamBookSessionListOut(BaseModel):
    items: list[IslamBookSessionOut]


class IslamBookSessionCreate(BaseModel):
    date: str
    pages: int = Field(ge=0)
    minutes: int | None = Field(default=None, ge=0)

    _date = field_validator("date")(iso_date)


# --- audio ----------------------------------------------------------------


class IslamAudioOut(BaseModel):
    id: str
    title: str
    creator: str | None = None
    description: str | None = None
    cover_url: str | None = None
    kind: str
    status: str
    created_at: str


class IslamAudioListOut(BaseModel):
    items: list[IslamAudioOut]


def _validated_kind(v: str) -> str:
    kind = (v or "").strip() or "audiobook"
    if kind not in AUDIO_KINDS:
        raise ValueError(f"kind must be one of {', '.join(AUDIO_KINDS)}")
    return kind


class IslamAudioCreate(BaseModel):
    title: str
    creator: str | None = None
    description: str | None = None
    kind: str = "audiobook"
    status: str = "reading"

    _title = field_validator("title")(_required_title)
    _kind = field_validator("kind")(_validated_kind)
    _status = field_validator("status")(_validated_status)
    _blanks = field_validator("creator", "description")(blank_to_none)


class IslamAudioUpdate(BaseModel):
    title: str | None = None
    creator: str | None = None
    description: str | None = None
    kind: str | None = None
    status: str | None = None

    _title = field_validator("title")(_required_title)
    _kind = field_validator("kind")(_validated_kind)
    _status = field_validator("status")(_validated_status)
    _blanks = field_validator("creator", "description")(blank_to_none)


class IslamAudioNoteOut(BaseModel):
    id: str
    audio_id: str
    date: str
    position: str | None = None
    body_md: str


class IslamAudioNoteListOut(BaseModel):
    items: list[IslamAudioNoteOut]


class IslamAudioNoteCreate(BaseModel):
    date: str
    position: str | None = None
    body_md: str = Field(default="", validation_alias=either_case("body_md"))

    _date = field_validator("date")(iso_date)
    _position = field_validator("position")(blank_to_none)


class IslamAudioSessionOut(BaseModel):
    id: str
    audio_id: str
    date: str
    minutes: int


class IslamAudioSessionListOut(BaseModel):
    items: list[IslamAudioSessionOut]


class IslamAudioSessionCreate(BaseModel):
    date: str
    minutes: int = Field(ge=0)

    _date = field_validator("date")(iso_date)
