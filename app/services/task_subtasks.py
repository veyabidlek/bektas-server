"""The checklist inside a task.

Its own module for the same reason `task_tags` is: `services.tasks` owns one
delicate invariant — `_apply_status` being the sole writer of `status`, `done`
and `done_at` — and nothing that has no business with task state should grow
inside it.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.task_subtask import TaskSubtask
from app.schemas.task_subtask import TaskSubtaskCreate, TaskSubtaskOut, TaskSubtaskUpdate
from app.services.calendar import ASTANA


def _now() -> str:
    return datetime.now(timezone.utc).astimezone(ASTANA).isoformat()


def out(sub: TaskSubtask) -> TaskSubtaskOut:
    return TaskSubtaskOut(
        id=sub.id, title=sub.title, done=sub.done, position=sub.position
    )


def get(db: Session, subtask_id: str) -> TaskSubtask | None:
    return db.query(TaskSubtask).filter(TaskSubtask.id == subtask_id).first()


def for_task(db: Session, task_id: str) -> list[TaskSubtask]:
    return (
        db.query(TaskSubtask)
        .filter(TaskSubtask.task_id == task_id)
        .order_by(TaskSubtask.position, TaskSubtask.created_at)
        .all()
    )


def for_many(db: Session, task_ids: list[str]) -> dict[str, list[TaskSubtask]]:
    """Every task's checklist in one query.

    A card shows «2/5», so doing this per task would put a query behind every
    row of a list that is already fetched whole.
    """
    if not task_ids:
        return {}
    rows = (
        db.query(TaskSubtask)
        .filter(TaskSubtask.task_id.in_(task_ids))
        .order_by(TaskSubtask.position, TaskSubtask.created_at)
        .all()
    )
    grouped: dict[str, list[TaskSubtask]] = {}
    for sub in rows:
        grouped.setdefault(sub.task_id, []).append(sub)
    return grouped


def create(db: Session, task_id: str, data: TaskSubtaskCreate) -> TaskSubtask:
    # New lines go to the end: a checklist is written top to bottom, and a step
    # that jumped to the front would be read as the next thing to do.
    last = (
        db.query(TaskSubtask)
        .filter(TaskSubtask.task_id == task_id)
        .order_by(TaskSubtask.position.desc())
        .first()
    )
    now = _now()
    sub = TaskSubtask(
        id=uuid.uuid4().hex[:8],
        task_id=task_id,
        title=data.title.strip(),
        done=False,
        position=(last.position + 1) if last else 0,
        created_at=now,
        updated_at=now,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def update(db: Session, sub: TaskSubtask, data: TaskSubtaskUpdate) -> TaskSubtask:
    fields = data.model_dump(exclude_unset=True)
    for field, value in fields.items():
        if value is not None:
            setattr(sub, field, value)
    sub.updated_at = _now()
    db.commit()
    db.refresh(sub)
    return sub


def remove(db: Session, sub: TaskSubtask) -> None:
    db.delete(sub)
    db.commit()


def remove_for_task(db: Session, task_id: str) -> None:
    """Drop a deleted task's checklist.

    ⚠️ By hand, not by ON DELETE CASCADE: SQLite honours that only under
    `PRAGMA foreign_keys`, which this app does not set, so the lines would
    outlive their task and re-attach to whatever reuses the id.
    """
    db.execute(delete(TaskSubtask).where(TaskSubtask.task_id == task_id))
    db.commit()
