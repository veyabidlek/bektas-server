from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InboxItem(Base):
    """A stray thought, link or photo, caught before it is decided about.

    The point is that capturing costs nothing: an item has no due date, no
    title and no category. Triage happens later, and turns the item into a
    task, a writing, a calendar event or a diary line — at which point
    `triaged_to` records what it became, so the inbox keeps a history rather
    than swallowing things.
    """

    __tablename__ = "inbox_items"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # "web" now, "telegram" when the bot lands — same convention as tasks.source,
    # deliberately a free string so a new source needs no migration.
    source: Mapped[str] = mapped_column(String, nullable=False, default="web")

    # None while untriaged, then "task:<id>" / "article:<slug>" / "event:<id>" /
    # "diary:<day>" / "dismissed". One string, so a new target type costs nothing.
    triaged_to: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    triaged_at: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    images: Mapped[list["InboxImage"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="InboxImage.sort_order",
    )


class InboxImage(Base):
    """A photo captured with an inbox item. Bytes on the volume, as everywhere."""

    __tablename__ = "inbox_images"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    item_id: Mapped[str] = mapped_column(
        String, ForeignKey("inbox_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    item: Mapped["InboxItem"] = relationship(back_populates="images")
