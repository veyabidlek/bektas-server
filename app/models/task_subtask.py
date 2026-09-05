from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TaskSubtask(Base):
    """One line of a task's checklist.

    ⚠️⚠️ **A subtask is deliberately NOT a task.** It has a title and a tick and
    nothing else — no status, no due date, no tags, no archive. That was
    Bektas's choice (2026-09-05) and it is also what keeps every existing count
    safe: the morning brief, the weekly digest, the dashboard card and the
    backlog all query `tasks`, so a row in THIS table cannot reach them by
    construction. Were subtasks rows in `tasks`, six queries would each need a
    filter and one omission would put a checklist line in tomorrow's brief.

    ⚠️ Ticking every line does not finish the parent. `services.tasks.
    _apply_status` is the only writer of `status`, `done` and `done_at`, and
    nothing here may become a second one.
    """

    __tablename__ = "task_subtasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: Order in the checklist. A checklist is a sequence — «buy the paint» then
    #: «paint the fence» — so the order is the user's, not the insert order's.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
