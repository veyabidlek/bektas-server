import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.task import Task
from app.schemas.task import TaskCreate, TaskOut, TaskTodaySummary, TaskUpdate
from app.services.calendar import ASTANA, normalize_dt

# How many tasks the dashboard card shows.
CARD_LIMIT = 4


def _now() -> str:
    return datetime.now(timezone.utc).astimezone(ASTANA).isoformat()


def today() -> str:
    return datetime.now(timezone.utc).astimezone(ASTANA).strftime("%Y-%m-%d")


def _normalize_due(due_at: str | None) -> str | None:
    """A due date is either a plain day or a full Almaty datetime.

    Reuses the calendar's normalizer, so "2026-08-20" stays a day and
    "2026-08-20T14:30" gains the +05:00 it implies.
    """
    if due_at is None:
        return None
    text = due_at.strip()
    if not text:
        return None
    return normalize_dt(text)


def _out(task: Task) -> TaskOut:
    return TaskOut(
        id=task.id,
        title=task.title,
        notes=task.notes or "",
        due_at=task.due_at,
        due_all_day=bool(task.due_at) and len(task.due_at or "") <= 10,
        done=task.done,
        done_at=task.done_at,
        source=task.source,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def out(task: Task) -> TaskOut:
    return _out(task)


def list_tasks(
    db: Session,
    include_done: bool = True,
    start: str | None = None,
    end: str | None = None,
) -> list[TaskOut]:
    """All tasks, or only those due inside [start, end).

    The range form is what the calendar asks for; it excludes undated tasks,
    which have no place on a calendar.
    """
    q = db.query(Task)
    if not include_done:
        q = q.filter(Task.done == False)  # noqa: E712
    if start or end:
        q = q.filter(Task.due_at.isnot(None))
        if start:
            q = q.filter(Task.due_at >= start)
        if end:
            q = q.filter(Task.due_at < end)

    tasks = q.order_by(Task.due_at.is_(None), Task.due_at.asc(), Task.created_at.asc()).all()
    return [_out(t) for t in tasks]


def today_summary(db: Session) -> TaskTodaySummary:
    """Due today plus anything already late — the dashboard's whole question."""
    day = today()
    open_tasks = [
        t
        for t in db.query(Task).filter(Task.done == False).all()  # noqa: E712
        if t.due_at
    ]

    overdue = [t for t in open_tasks if t.due_at[:10] < day]
    due_today = [t for t in open_tasks if t.due_at[:10] == day]

    # Late things first, then today's, earliest due first within each.
    ordered = sorted(overdue, key=lambda t: t.due_at) + sorted(
        due_today, key=lambda t: t.due_at
    )

    return TaskTodaySummary(
        today=day,
        overdue_count=len(overdue),
        today_count=len(due_today),
        tasks=[_out(t) for t in ordered[:CARD_LIMIT]],
    )


def get_task(db: Session, task_id: str) -> Task | None:
    return db.query(Task).filter(Task.id == task_id).first()


def create_task(db: Session, data: TaskCreate) -> Task:
    now = _now()
    task = Task(
        id=uuid.uuid4().hex[:8],
        title=data.title.strip(),
        notes=(data.notes or "").strip(),
        due_at=_normalize_due(data.due_at),
        done=False,
        source=(data.source or "web").strip() or "web",
        created_at=now,
        updated_at=now,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def update_task(db: Session, task: Task, data: TaskUpdate) -> Task:
    fields = data.model_dump(exclude_unset=True)

    if "title" in fields and isinstance(fields["title"], str):
        fields["title"] = fields["title"].strip()
    if "notes" in fields and isinstance(fields["notes"], str):
        fields["notes"] = fields["notes"].strip()
    if "due_at" in fields:
        fields["due_at"] = _normalize_due(fields["due_at"])
    if "done" in fields and fields["done"] is not None:
        _apply_done(task, bool(fields["done"]))
        fields.pop("done")

    for field, value in fields.items():
        setattr(task, field, value)

    task.updated_at = _now()
    db.commit()
    db.refresh(task)
    return task


def _apply_done(task: Task, done: bool) -> None:
    task.done = done
    # done_at is cleared on un-ticking so the "recently finished" ordering never
    # shows a stale timestamp for an open task.
    task.done_at = _now() if done else None


def set_done(db: Session, task: Task, done: bool | None = None) -> Task:
    """Set the flag, or flip it when `done` is not given."""
    _apply_done(task, (not task.done) if done is None else done)
    task.updated_at = _now()
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task: Task) -> None:
    db.delete(task)
    db.commit()
