from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Article(Base):
    __tablename__ = "articles"

    slug: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    date: Mapped[str] = mapped_column(String, nullable=False)
    read_time: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[list] = mapped_column(JSON, nullable=False)

    comments: Mapped[list["Comment"]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
        order_by="Comment.id",
    )


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    article_slug: Mapped[str] = mapped_column(
        String, ForeignKey("articles.slug"), nullable=False
    )
    author: Mapped[str] = mapped_column(String, nullable=False)
    avatar: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    article: Mapped["Article"] = relationship(back_populates="comments")
