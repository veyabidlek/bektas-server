from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.models.reading import STATUSES


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


class ReadingListOut(BaseModel):
    """The list endpoint answers with an object, not a bare array.

    Wrapping leaves room to add a total or a facet later without breaking a
    client that is already parsing the response.
    """

    items: list[ReadingItemOut]


class ReadingItemIn(BaseModel):
    """The body of both POST and PUT — a create and a full update take the
    same shape, so there is one schema and no drift between them."""

    title: str
    author: str | None = None
    category: str | None = None
    status: str = "not_started"
    pages: int | None = Field(default=None, ge=0)
    score: int | None = Field(default=None, ge=1, le=5)
    started: str | None = None
    completed: str | None = None

    @field_validator("title")
    @classmethod
    def _title_is_required(cls, v: str) -> str:
        title = (v or "").strip()
        if not title:
            raise ValueError("Title is required")
        return title

    @field_validator("author", "category")
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
