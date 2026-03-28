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


class PortfolioProjectCreate(BaseModel):
    id: str
    title: str
    description: str = ""
    screenshot_url: str | None = None
    website_url: str | None = None
    github_url: str | None = None
    stack: list[str] = []
    sort_order: int = 0


class PortfolioProjectUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    screenshot_url: str | None = None
    website_url: str | None = None
    github_url: str | None = None
    stack: list[str] | None = None
    sort_order: int | None = None
