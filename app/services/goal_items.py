"""The two things inside a goal: nodes (boxes in the tree) and tasks.

Split out of `goals.py` at the 150-line service cap. Shares that module's
clock and deadline normalizer so there is one of each.
"""

import uuid

from sqlalchemy.orm import Session

from app.models.goal import Goal, GoalNode, GoalTask
from app.schemas.goal import (
    GoalNodeCreate,
    GoalNodeUpdate,
    GoalTaskCreate,
    GoalTaskUpdate,
)
from app.services import goals_tree as tree
from app.services.goals import normalize_due, now_iso


def add_node(db: Session, goal_id: str, data: GoalNodeCreate) -> GoalNode | None:
    if db.get(Goal, goal_id) is None:
        return None
    siblings = [
        {"position": n.position}
        for n in db.query(GoalNode)
        .filter(GoalNode.goal_id == goal_id, GoalNode.parent_id == data.parent_id)
        .all()
    ]
    now = now_iso()
    node = GoalNode(
        id=str(uuid.uuid4()),
        goal_id=goal_id,
        parent_id=data.parent_id,
        title=data.title.strip(),
        description=data.description or "",
        position=tree.next_position(siblings),
        created_at=now,
        updated_at=now,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _is_descendant(db: Session, candidate_id: str, ancestor_id: str) -> bool:
    """Walks up from `candidate_id`. The `seen` set is not paranoia — a cycle
    already in the table would otherwise hang the request rather than fail it."""
    seen: set[str] = set()
    current = db.get(GoalNode, candidate_id)
    while current is not None and current.id not in seen:
        if current.parent_id == ancestor_id:
            return True
        seen.add(current.id)
        current = db.get(GoalNode, current.parent_id) if current.parent_id else None
    return False


def update_node(db: Session, node_id: str, data: GoalNodeUpdate) -> GoalNode | None:
    node = db.get(GoalNode, node_id)
    if node is None:
        return None
    if data.title is not None:
        node.title = data.title.strip()
    if data.description is not None:
        node.description = data.description
    if data.parent_id is not None:
        # A node may not become its own descendant: that detaches the subtree
        # from every read at once, and `nest()` would quietly redraw it as a
        # second root rather than report anything wrong.
        if data.parent_id == node_id or _is_descendant(db, data.parent_id, node_id):
            return None
        node.parent_id = data.parent_id or None
    node.updated_at = now_iso()
    db.commit()
    db.refresh(node)
    return node


def delete_node(db: Session, node_id: str) -> bool:
    """Deletes the node and everything under it.

    The walk is explicit rather than a database cascade because SQLite does not
    enforce foreign keys by default — a cascade that silently does nothing
    would leave orphans that `nest()` then draws as extra roots.
    """
    node = db.get(GoalNode, node_id)
    if node is None:
        return False
    for child in db.query(GoalNode).filter(GoalNode.parent_id == node_id).all():
        delete_node(db, child.id)
    db.delete(node)  # its tasks cascade through the relationship
    db.commit()
    return True


def add_task(db: Session, node_id: str, data: GoalTaskCreate) -> GoalTask | None:
    if db.get(GoalNode, node_id) is None:
        return None
    siblings = [
        {"position": t.position}
        for t in db.query(GoalTask).filter(GoalTask.node_id == node_id).all()
    ]
    now = now_iso()
    task = GoalTask(
        id=str(uuid.uuid4()),
        node_id=node_id,
        title=data.title.strip(),
        description=data.description or "",
        due_at=normalize_due(data.due_at),
        position=tree.next_position(siblings),
        created_at=now,
        updated_at=now,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _set_done(task: GoalTask, done: bool) -> None:
    """`done_at` is stamped on the way in and CLEARED on the way out — a
    lingering timestamp on an unticked task reads as finished to every later
    query that trusts it."""
    task.done = done
    task.done_at = now_iso() if done else None


def update_task(db: Session, task_id: str, data: GoalTaskUpdate) -> GoalTask | None:
    task = db.get(GoalTask, task_id)
    if task is None:
        return None
    if data.title is not None:
        task.title = data.title.strip()
    if data.description is not None:
        task.description = data.description
    if data.due_at is not None:
        task.due_at = normalize_due(data.due_at)
    if data.done is not None:
        _set_done(task, data.done)
    task.updated_at = now_iso()
    db.commit()
    db.refresh(task)
    return task


def toggle_task(db: Session, task_id: str) -> GoalTask | None:
    task = db.get(GoalTask, task_id)
    if task is None:
        return None
    _set_done(task, not task.done)
    task.updated_at = now_iso()
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task_id: str) -> bool:
    task = db.get(GoalTask, task_id)
    if task is None:
        return False
    db.delete(task)
    db.commit()
    return True
