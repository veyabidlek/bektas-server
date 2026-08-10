from pydantic import BaseModel


class PortfolioProjectOut(BaseModel):
    id: str
    title: str
    description: str
    screenshot_url: str | None
    website_url: str | None
    github_url: str | None
    stack: list[str]
    featured: bool
    sort_order: int
    archived: bool
    visibility: str = "public"


class PortfolioProjectCreate(BaseModel):
    id: str
    title: str
    description: str = ""
    screenshot_url: str | None = None
    website_url: str | None = None
    github_url: str | None = None
    stack: list[str] = []
    sort_order: int = 0
    visibility: str = "public"


class PortfolioImageOut(BaseModel):
    """A hosted screenshot. `url` is ready to drop straight into
    `screenshot_url` — it is the same-origin route that serves the bytes."""

    id: str
    url: str
    width: int | None = None
    height: int | None = None
    created_at: str


class PortfolioProjectUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    screenshot_url: str | None = None
    website_url: str | None = None
    github_url: str | None = None
    stack: list[str] | None = None
    sort_order: int | None = None
    visibility: str | None = None
