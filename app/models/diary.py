from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DiaryEntry(Base):
    """One entry per day. The day *is* the identity — writing again on the same
    date edits that day rather than creating a second row, which is what makes
    the "open the diary, land on today" flow work without any create/update
    decision in the UI.

    Body is markdown, the same format articles use (`body_md`) — one text
    format on this site, not two.
    """

    __tablename__ = "diary_entries"

    day: Mapped[str] = mapped_column(String, primary_key=True)  # YYYY-MM-DD, Almaty
    body_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    images: Mapped[list["DiaryImage"]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="DiaryImage.sort_order",
    )


class DiaryImage(Base):
    """A photo attached to a day.

    The bytes live on the Docker volume (``/data/uploads/diary``), not in
    SQLite — a database that grows by megabytes per photo would make every
    backup heavier for no benefit. Only the metadata is here.
    """

    __tablename__ = "diary_images"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    day: Mapped[str] = mapped_column(
        String, ForeignKey("diary_entries.day", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    entry: Mapped["DiaryEntry"] = relationship(back_populates="images")
