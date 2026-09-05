from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TaskTag(Base):
    """A label a task can wear — in practice, one of Bektas's projects.

    Managed rather than free text (his choice, 2026-09-05): the tag is a row,
    so renaming «Shakyrtu» to «Shakyrtu.kz» is one edit instead of a sweep over
    every task, and a typo cannot quietly create a second project.

    ⚠️ `name` is unique **case-insensitively**, which SQLite will not enforce
    for us on a plain unique index — `services.task_tags` compares the folded
    name before writing. The index below is the second line of defence, not the
    first.
    """

    __tablename__ = "task_tags"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)

    #: A key from the client's fixed palette, not a hex string. A closed set
    #: keeps the board's chips looking like one design; a free colour field is
    #: how a board ends up with eleven barely-different greys.
    color: Mapped[str] = mapped_column(String, nullable=False, default="slate")

    #: Order in the picker and the filter bar, so the projects Bektas works on
    #: most can sit first without being renamed.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class TaskTagLink(Base):
    """Which tasks wear which tags.

    A join table rather than a column on `tasks`, because a task carries
    several tags and because it keeps `tasks` untouched — that table already
    holds three columns (`status`, `done`, `done_at`) that only
    `services.tasks._apply_status` may write, and the safest way to honour that
    rule is to not add a fourth reason to write to the row at all.

    ⚠️ The primary key is the PAIR, so tagging a task twice with the same tag
    is impossible rather than merely tidied up afterwards.

    ⚠️ Both foreign keys cascade, and that is the whole contract of this table:
    deleting a tag drops its links and leaves the tasks; deleting a task drops
    its links and leaves the tags. Neither end may take the other with it.
    """

    __tablename__ = "task_tag_links"

    task_id: Mapped[str] = mapped_column(
        String, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    tag_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("task_tags.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
