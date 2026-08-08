from pydantic import BaseModel


class InboxImageOut(BaseModel):
    id: str
    item_id: str
    url: str
    width: int | None = None
    height: int | None = None
    created_at: str


class InboxItemOut(BaseModel):
    id: str
    text: str = ""
    source: str = "web"
    triaged_to: str | None = None
    # Split out of `triaged_to` so the client does not parse strings.
    triaged_kind: str | None = None
    triaged_id: str | None = None
    triaged_at: str | None = None
    images: list[InboxImageOut] = []
    created_at: str
    updated_at: str


class InboxItemCreate(BaseModel):
    text: str = ""
    source: str = "web"


class InboxItemUpdate(BaseModel):
    text: str


class TriageRequest(BaseModel):
    """What to turn the item into.

    Extra fields are per-target: a task may carry a due date, an event needs a
    start, and both can override the title taken from the item's first line.
    """

    kind: str
    title: str | None = None
    due_at: str | None = None
    starts_at: str | None = None
    reminder_minutes: int | None = None


class TriageResult(BaseModel):
    item: InboxItemOut
    kind: str
    # The object that now exists, if the triage created one.
    target_id: str | None = None


class InboxCount(BaseModel):
    untriaged: int
