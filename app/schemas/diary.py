from pydantic import BaseModel


class DiaryImageOut(BaseModel):
    id: str
    day: str
    width: int | None = None
    height: int | None = None
    created_at: str


class DiaryEntryOut(BaseModel):
    day: str
    body_md: str = ""
    # False when the day has never been written. The GET still returns 200 with
    # an empty shell so the editor can open on any date without special-casing.
    exists: bool = True
    images: list[DiaryImageOut] = []
    created_at: str | None = None
    updated_at: str | None = None


class DiaryEntrySummary(BaseModel):
    day: str
    preview: str
    image_count: int
    updated_at: str


class DiaryEntryUpdate(BaseModel):
    body_md: str = ""
