import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.task import Task
from app.schemas.task import TaskCreate, TaskOut, TaskTodaySummary, TaskUpdate
from app.services import task_rules, task_subtasks, task_tag_links, task_tags
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


def _out(task: Task, tags=(), subtasks=()) -> TaskOut:
    status = task.status or task_rules.TODO
    return TaskOut(
        id=task.id,
        title=task.title,
        notes=task.notes or "",
        due_at=task.due_at,
        due_all_day=bool(task.due_at) and len(task.due_at or "") <= 10,
        status=status,
        done=task_rules.is_done(status),
        done_at=task.done_at,
        urgent=task.urgent,
        important=task.important,
        quadrant=task_rules.quadrant(task.urgent, task.important),
        archived_at=task.archived_at,
        source=task.source,
        tags=[task_tags.out(t) for t in tags],
        subtasks=[task_subtasks.out(s) for s in subtasks],
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def out(task: Task, db: Session | None = None) -> TaskOut:
    """One task, with its tags when a session is on hand to read them.

    The session is optional so the older callers that only ever wanted the
    task's own columns keep working; every route that returns a task to the
    board passes it, because a card with no chips looks like a task with no
    project.
    """
    tags = task_tag_links.tags_for(db, task.id) if db is not None else ()
    subs = task_subtasks.for_task(db, task.id) if db is not None else ()
    return _out(task, tags, subs)


# --------------------------------------------------------------- the funnel


def _apply_status(task: Task, status: str) -> None:
    """⚠️ THE ONLY WRITER of `status`, `done` and `done_at`. Keep it that way.

    Three columns, one decision. `done` is a denormalized copy of
    `status == "done"` (four SQL filters across the bot and the weekly digest
    read it), and `done_at` is stamped on the way in and **cleared on the way
    out** so "recently completed" ordering never shows a timestamp belonging to
    work that is open again.

    Re-entering Done does NOT re-stamp: dragging a card Done → In Progress →
    Done is a correction, and it should not rewrite when the thing was
    actually finished.
    """
    task.status = task_rules.normalize_status(status)
    was_done = bool(task.done)
    task.done = task_rules.is_done(task.status)
    if not task.done:
        task.done_at = None
    elif not was_done or not task.done_at:
        task.done_at = _now()


# ------------------------------------------------------------------- reads


def list_tasks(
    db: Session,
    include_done: bool = True,
    start: str | None = None,
    end: str | None = None,
    include_archived: bool = False,
) -> list[TaskOut]:
    """All tasks, or only those due inside [start, end).

    The range form is what the calendar asks for; it excludes undated tasks,
    which have no place on a calendar.

    Archived tasks are absent unless asked for — that is the whole point of
    archiving, and it is also the codebase's `include_archived` convention.
    """
    q = db.query(Task)
    if not include_archived:
        q = q.filter(Task.archived_at.is_(None))
    if not include_done:
        q = q.filter(Task.done == False)  # noqa: E712
    if start or end:
        q = q.filter(Task.due_at.isnot(None))
        if start:
            q = q.filter(Task.due_at >= start)
        if end:
            q = q.filter(Task.due_at < end)

    tasks = q.order_by(Task.due_at.is_(None), Task.due_at.asc(), Task.created_at.asc()).all()
    # One query for every task's tags rather than one per card.
    ids = [t.id for t in tasks]
    by_task = task_tag_links.tags_for_many(db, ids)
    subs = task_subtasks.for_many(db, ids)
    return [_out(t, by_task.get(t.id, ()), subs.get(t.id, ())) for t in tasks]


def today_summary(db: Session) -> TaskTodaySummary:
    """Due today plus anything already late — the dashboard's whole question."""
    day = today()
    open_tasks = [
        t
        for t in db.query(Task)
        .filter(Task.done == False, Task.archived_at.is_(None))  # noqa: E712
        .all()
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


# ------------------------------------------------------------------ writes


def create_task(db: Session, data: TaskCreate) -> Task:
    now = _now()
    task = Task(
        id=uuid.uuid4().hex[:8],
        title=data.title.strip(),
        notes=(data.notes or "").strip(),
        due_at=_normalize_due(data.due_at),
        urgent=data.urgent,
        important=data.important,
        source=(data.source or "web").strip() or "web",
        created_at=now,
        updated_at=now,
    )
    # Through the funnel even on create: a task made straight into Done (the
    # board's "add here" affordance) has to get its done_at like any other.
    _apply_status(task, data.status or task_rules.TODO)
    db.add(task)
    db.commit()
    db.refresh(task)
    # After the insert: a link needs a task id to point at.
    if data.tag_ids is not None:
        task_tag_links.set_tags(db, task.id, data.tag_ids)
    return task


def update_task(db: Session, task: Task, data: TaskUpdate) -> Task:
    fields = data.model_dump(exclude_unset=True)

    if "title" in fields and isinstance(fields["title"], str):
        fields["title"] = fields["title"].strip()
    if "notes" in fields and isinstance(fields["notes"], str):
        fields["notes"] = fields["notes"].strip()
    if "due_at" in fields:
        fields["due_at"] = _normalize_due(fields["due_at"])

    # `status` wins over `done`: the board is the richer instrument, and the
    # router refuses a body carrying both, so this only ever resolves a caller
    # sending one of them.
    # ⚠️ Out of `fields` before the setattr loop below: `tag_ids` lives in a
    # join table, not on the row, and setattr would quietly attach a stray
    # attribute that never reaches the database.
    tag_ids = fields.pop("tag_ids", None)

    status = fields.pop("status", None)
    done = fields.pop("done", None)
    if status is not None:
        _apply_status(task, status)
    elif done is not None:
        _apply_status(task, task_rules.status_for_done(bool(done)))

    for field, value in fields.items():
        setattr(task, field, value)

    task.updated_at = _now()
    db.commit()
    db.refresh(task)
    if tag_ids is not None:
        task_tag_links.set_tags(db, task.id, tag_ids)
    return task


def set_status(db: Session, task: Task, status: str) -> Task:
    """What a drag between board columns commits."""
    _apply_status(task, status)
    task.updated_at = _now()
    db.commit()
    db.refresh(task)
    return task


def set_done(db: Session, task: Task, done: bool | None = None) -> Task:
    """Tick the box, or flip it when `done` is not given.

    The checkbox on the calendar and in the list predates the board; it still
    speaks booleans and is translated here rather than at each call site.
    """
    target = (not task.done) if done is None else done
    return set_status(db, task, task_rules.status_for_done(bool(target)))


def set_priority(db: Session, task: Task, urgent: bool | None, important: bool | None) -> Task:
    """Place the task in the matrix. Both axes, every time — see the schema."""
    task.urgent = urgent
    task.important = important
    task.updated_at = _now()
    db.commit()
    db.refresh(task)
    return task


def set_archived(db: Session, task: Task, archived: bool | None = None) -> Task:
    """Out of the way, or back. Nothing else about the task changes.

    Archiving is deliberately NOT completion: an abandoned task is archived
    while still `todo`, and the Archive shows it as such. Conflating the two
    would make "what did I actually finish?" unanswerable.
    """
    target = (task.archived_at is None) if archived is None else archived
    task.archived_at = _now() if target else None
    task.updated_at = _now()
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task: Task) -> None:
    # ⚠️ The links go first, and by hand. SQLite only enforces ON DELETE
    # CASCADE when `PRAGMA foreign_keys` is on and this app leaves it off, so
    # the rows would otherwise survive their task and re-appear the moment an
    # id is reused.
    task_tag_links.unlink_task(db, task.id)
    task_subtasks.remove_for_task(db, task.id)
    db.delete(task)
    db.commit()
