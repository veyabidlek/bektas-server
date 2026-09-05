"""Which tasks wear which tags.

Split from `task_tags` because they are two jobs: that module owns the tag
rows — their names, colours and order — and this one owns the join. The house
rule is 150 lines a service, and the split that keeps both under it is also the
one that matches the two tables.
"""

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.task_tag import TaskTag, TaskTagLink
from app.services.task_tags import get_tag


class UnknownTag(Exception):
    """A task was handed a tag id that does not exist."""

    def __init__(self, tag_id: str):
        super().__init__(tag_id)
        self.tag_id = tag_id



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
