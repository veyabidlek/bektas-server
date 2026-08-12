from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Goal(Base):
    """A roadmap — the whole tree of what it takes to get somewhere.

    Progress is never stored: a goal's percentage is its done tasks over its
    total, computed on read. Anything cached here would be a second source of
    truth that goes stale the first time a task is ticked from the bot.
    """

    __tablename__ = "goals"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    nodes: Mapped[list["GoalNode"]] = relationship(
        back_populates="goal",
        cascade="all, delete-orphan",
    )


class GoalNode(Base):
    """One box in the roadmap.

    `parent_id` NULL means a root — a goal may have several, which is what
    makes the picture a fan of areas rather than one trunk.

    There is deliberately no x/y here. The layout is derived from the tree at
    render time, so adding a node can never leave the drawing stale, and there
    is nothing to drag on a phone.
    """

    __tablename__ = "goal_nodes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    goal_id: Mapped[str] = mapped_column(
        String, ForeignKey("goals.id"), nullable=False, index=True
    )
    parent_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("goal_nodes.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: Order among siblings. Sparse on purpose — inserting between two nodes
    #: takes the gap rather than renumbering the row's neighbours.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    goal: Mapped["Goal"] = relationship(back_populates="nodes")
    tasks: Mapped[list["GoalTask"]] = relationship(
        back_populates="node",
        cascade="all, delete-orphan",
    )


class GoalTask(Base):
    """A subtask inside a node: the thing actually done, and when it is due.

    `due_at` carries the same two shapes as `tasks.due_at` — a plain
    "YYYY-MM-DD" or a full ISO datetime with the Almaty offset — so a goal's
    deadlines can join the calendar's day column later without translating.
    """

    __tablename__ = "goal_tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    node_id: Mapped[str] = mapped_column(
        String, ForeignKey("goal_nodes.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    #: The text that opens when the subtask is clicked. Markdown.
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    done_at: Mapped[str | None] = mapped_column(String, nullable=True)
    due_at: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    node: Mapped["GoalNode"] = relationship(back_populates="tasks")
