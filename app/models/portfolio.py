from sqlalchemy import Boolean, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PortfolioProject(Base):
    __tablename__ = "portfolio_projects"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    screenshot_url: Mapped[str | None] = mapped_column(String, nullable=True)
    website_url: Mapped[str | None] = mapped_column(String, nullable=True)
    github_url: Mapped[str | None] = mapped_column(String, nullable=True)
    stack: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    visibility: Mapped[str] = mapped_column(String, nullable=False, default="public")


class PortfolioImage(Base):
    """A hosted screenshot for the projects page.

    Deliberately **not** bound to a project. The add-project form needs a
    screenshot URL *before* the project row exists, so an upload has to stand on
    its own; `portfolio_projects.screenshot_url` merely points at one of these
    (or at an external URL — that path stays open).

    Bytes go to the Docker volume (``/data/uploads/portfolio``), metadata here,
    exactly like the diary's and a writing's photos. Serving is **public**: a
    project card is public content, and an `<img>` on /projects has to load for
    a logged-out reader.
    """

    __tablename__ = "portfolio_images"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
