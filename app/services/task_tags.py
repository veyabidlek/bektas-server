"""Managing tags, and attaching them to tasks.

Kept out of `services.tasks` on purpose. That module owns one delicate
invariant — `_apply_status` being the sole writer of `status`, `done` and
`done_at` — and the way to keep that readable is to not grow it with anything
that has nothing to do with task state.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.task_tag import TaskTag, TaskTagLink
from app.schemas.task_tag import TaskTagCreate, TaskTagOut, TaskTagUpdate
from app.services.calendar import ASTANA


class TagNameTaken(Exception):
    """Another tag already answers to this name, whatever the case."""


class UnknownTag(Exception):
    """A task was handed a tag id that does not exist."""

    def __init__(self, tag_id: str):
        super().__init__(tag_id)
        self.tag_id = tag_id


def _now() -> str:
    return datetime.now(timezone.utc).astimezone(ASTANA).isoformat()


def _fold(name: str) -> str:
    """The form two names are compared in: trimmed and case-folded.

    ⚠️ SQLite's unique index is byte-wise, so «Tapsyr» and «tapsyr» would both
    fit through it. Uniqueness is therefore decided here, before the write.
    """
    return " ".join(name.split()).casefold()


def out(tag: TaskTag) -> TaskTagOut:
    return TaskTagOut(id=tag.id, name=tag.name, color=tag.color, position=tag.position)


# ------------------------------------------------------------------ the tags


def list_tags(db: Session) -> list[TaskTag]:
    return db.query(TaskTag).order_by(TaskTag.position, TaskTag.name).all()


def get_tag(db: Session, tag_id: str) -> TaskTag | None:
    return db.query(TaskTag).filter(TaskTag.id == tag_id).first()


def _name_clashes(db: Session, name: str, *, ignoring: str | None = None) -> bool:
    folded = _fold(name)
    for existing in db.query(TaskTag).all():
        if ignoring is not None and existing.id == ignoring:
            continue
        if _fold(existing.name) == folded:
            return True
    return False


def create_tag(db: Session, data: TaskTagCreate) -> TaskTag:
    name = " ".join(data.name.split())
    if _name_clashes(db, name):
        raise TagNameTaken(name)

    now = _now()
    # New tags go to the end of the picker rather than the front: the order is
    # Bektas's to arrange, and a new project should not jump the queue.
    last = db.query(TaskTag).order_by(TaskTag.position.desc()).first()
    tag = TaskTag(
        id=uuid.uuid4().hex[:8],
        name=name,
        color=(data.color or "slate").strip() or "slate",
        position=(last.position + 1) if last else 0,
        created_at=now,
        updated_at=now,
    )
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


def update_tag(db: Session, tag: TaskTag, data: TaskTagUpdate) -> TaskTag:
    fields = data.model_dump(exclude_unset=True)

    if "name" in fields and fields["name"] is not None:
        name = " ".join(fields["name"].split())
        if _name_clashes(db, name, ignoring=tag.id):
            raise TagNameTaken(name)
        fields["name"] = name

    for field, value in fields.items():
        if value is not None:
            setattr(tag, field, value)

    tag.updated_at = _now()
    db.commit()
    db.refresh(tag)
    return tag


def delete_tag(db: Session, tag: TaskTag) -> None:
    """Drop the tag and its links — and nothing else.

    ⚠️ The links are removed explicitly rather than left to the FK's ON DELETE
    CASCADE, because SQLite only honours that when `PRAGMA foreign_keys` is on,
    and this app does not turn it on. Relying on the database here would leave
    orphaned rows that quietly re-tag the next tag to reuse the id.
    """
    db.execute(delete(TaskTagLink).where(TaskTagLink.tag_id == tag.id))
    db.delete(tag)
    db.commit()


# ---------------------------------------------------- tags on a task


def tags_for(db: Session, task_id: str) -> list[TaskTag]:
    return (
        db.query(TaskTag)
        .join(TaskTagLink, TaskTagLink.tag_id == TaskTag.id)
        .filter(TaskTagLink.task_id == task_id)
        .order_by(TaskTag.position, TaskTag.name)
        .all()
    )


def tags_for_many(db: Session, task_ids: list[str]) -> dict[str, list[TaskTag]]:
    """Every task's tags in one query.

    The board draws a chip on each card, so doing this per task would put a
    query behind every row of a list that is already fetched whole.
    """
    if not task_ids:
        return {}
    rows = (
        db.query(TaskTagLink.task_id, TaskTag)
        .join(TaskTag, TaskTag.id == TaskTagLink.tag_id)
        .filter(TaskTagLink.task_id.in_(task_ids))
        .order_by(TaskTag.position, TaskTag.name)
        .all()
    )
    grouped: dict[str, list[TaskTag]] = {}
    for task_id, tag in rows:
        grouped.setdefault(task_id, []).append(tag)
    return grouped


def set_tags(db: Session, task_id: str, tag_ids: list[str]) -> None:
    """Replace a task's tags with exactly this set.

    Replace rather than add/remove verbs: the picker sends what the task should
    wear, and one shape of write is one shape of bug.

    ⚠️ An id that names no tag raises instead of being skipped. Dropping it
    silently would let a stale picker quietly un-file a task, and the caller
    would see a 200.
    """
    wanted: list[str] = []
    for tag_id in tag_ids:
        if tag_id in wanted:
            continue  # the same tag twice is one tag
        if get_tag(db, tag_id) is None:
            raise UnknownTag(tag_id)
        wanted.append(tag_id)

    db.execute(delete(TaskTagLink).where(TaskTagLink.task_id == task_id))
    for tag_id in wanted:
        db.add(TaskTagLink(task_id=task_id, tag_id=tag_id))
    db.commit()


def unlink_task(db: Session, task_id: str) -> None:
    """Forget a deleted task's tags, keeping the tags themselves."""
    db.execute(delete(TaskTagLink).where(TaskTagLink.task_id == task_id))
    db.commit()
