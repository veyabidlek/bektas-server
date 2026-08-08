from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ArticleImage(Base):
    """A photo attached to a writing.

    Same storage shape as the diary's: bytes on the Docker volume, metadata
    here. The difference is who may see it — an article has a visibility level,
    and the serving route mirrors it rather than assuming admin-only.
    """

    __tablename__ = "article_images"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    article_slug: Mapped[str] = mapped_column(
        String, ForeignKey("articles.slug"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
