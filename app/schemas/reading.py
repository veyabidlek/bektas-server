from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.reading import STATUSES

# Generic helpers that happen to have been written for the Islam section — the
# camelCase-or-snake_case alias and the one date format. Imported rather than
# copied: a second `either_case` is the one that would drift.
from app.schemas.islam import either_case, iso_date


class ReadingItemOut(BaseModel):
    id: int
    title: str
    author: str | None = None
    category: str | None = None
    status: str = "not_started"
    pages: int | None = None
    score: int | None = None
    # ISO "YYYY-MM-DD", or nothing.
    started: str | None = None
    completed: str | None = None
    created_at: str
    # The Shelf view (2026-08-10). `cover_url` is the public serving route, or
    # None — never a path on disk, so the client can tell "no picture" from
    # "broken picture".
    description: str | None = None
    cover_url: str | None = None
    # "public" / "friends" / "private". Private since 2026-08-17 — the shelf
    # used to be open and is not any more.
    visibility: str = "private"


class ReadingListOut(BaseModel):
    """The list endpoint answers with an object, not a bare array.

    Wrapping leaves room to add a total or a facet later without breaking a
    client that is already parsing the response.
    """

    items: list[ReadingItemOut]


class ReadingItemIn(BaseModel):
    """The body of both POST and PUT — a create and a full update take the
    same shape, so there is one schema and no drift between them.

    The cover is **not** here: it arrives as multipart on its own route, so a
    PUT that knows nothing about it must leave `cover_image` alone rather than
    replace-to-nothing like every other field.
    """

    title: str
    author: str | None = None
    category: str | None = None
    status: str = "not_started"
    pages: int | None = Field(default=None, ge=0)
    score: int | None = Field(default=None, ge=1, le=5)
    started: str | None = None
    completed: str | None = None
    description: str | None = None

    @field_validator("title")
    @classmethod
    def _title_is_required(cls, v: str) -> str:
        title = (v or "").strip()
        if not title:
            raise ValueError("Title is required")
        return title

    @field_validator("author", "category", "description")
    @classmethod
    def _blank_is_nothing(cls, v: str | None) -> str | None:
        """An empty string from a form field means "not set", not "".

        The import produces real Nones; a browser sends "". Both have to land
        as NULL or the client gets an empty author to render.
        """
        if v is None:
            return None
        return v.strip() or None

    @field_validator("status")
    @classmethod
    def _status_is_known(cls, v: str) -> str:
        status = (v or "").strip() or "not_started"
        if status not in STATUSES:
            raise ValueError(f"status must be one of {', '.join(STATUSES)}")
        return status

    @field_validator("started", "completed")
    @classmethod
    def _dates_are_iso(cls, v: str | None) -> str | None:
        if v is None:
            return None
        raw = v.strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw).isoformat()
        except ValueError as exc:
            raise ValueError(f"{raw!r} is not an ISO date (YYYY-MM-DD)") from exc


# --- notes and sessions ----------------------------------------------------
# Both are **admin-only**, unlike the shelf they hang off: what he is reading
# is public, what he wrote about it is not.
#
# The create bodies take camelCase alongside snake_case wherever the name has
# more than one word — `lib/api.ts` sends `pageFrom` / `pageTo` / `bodyMd` and
# its `fetchApi` does not snake-case outgoing bodies. Responses stay snake_case
# like every other resource here.
    visibility: str = "private"


class ReadingNoteOut(BaseModel):
    id: int
    item_id: int
    date: str
    page_from: int | None = None
    page_to: int | None = None
    body_md: str


class ReadingNoteListOut(BaseModel):
    items: list[ReadingNoteOut]


class ReadingNoteIn(BaseModel):
    date: str
    page_from: int | None = Field(
        default=None, ge=1, validation_alias=either_case("page_from")
    )
    page_to: int | None = Field(default=None, ge=1, validation_alias=either_case("page_to"))
    body_md: str = Field(default="", validation_alias=either_case("body_md"))

    _date = field_validator("date")(iso_date)

    @model_validator(mode="after")
    def _range_reads_forwards(self) -> "ReadingNoteIn":
        """Only when both ends are given — one-sided ranges are legitimate
        ("from page 12 onwards") and open-ended notes are the common case."""
        if self.page_from is not None and self.page_to is not None:
            if self.page_from > self.page_to:
                raise ValueError("page_from must not be greater than page_to")
        return self


class ReadingSessionOut(BaseModel):
    id: int
    item_id: int
    date: str
    pages: int
    minutes: int | None = None


class ReadingSessionListOut(BaseModel):
    items: list[ReadingSessionOut]


class ReadingSessionIn(BaseModel):
    date: str
    pages: int = Field(ge=0)
    minutes: int | None = Field(default=None, ge=0)

    _date = field_validator("date")(iso_date)
