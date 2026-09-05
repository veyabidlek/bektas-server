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
