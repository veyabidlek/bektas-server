"""Goals: the roadmap itself and how it reads back.

Nodes and tasks live in `goal_items.py` — this file is the goal and its tree
assembly, which is already most of a screen. `now_iso` and `normalize_due` are
public because that module needs them and one clock is better than two.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.goal import Goal, GoalNode, GoalTask
from app.schemas.goal import GoalCreate, GoalDetail, GoalOut, GoalUpdate
from app.services import goals_tree as tree
from app.services.calendar import ASTANA, normalize_dt


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone(ASTANA).isoformat()


def normalize_due(due_at: str | None) -> str | None:
    """A deadline is either a plain day or a full Almaty datetime — the same
    normalizer the calendar and tasks use, so the shapes stay identical."""
    text = (due_at or "").strip()
    return normalize_dt(text) if text else None


def task_dict(t: GoalTask) -> dict[str, Any]:
    return {
        "id": t.id,
        "node_id": t.node_id,
        "title": t.title,
        "description": t.description or "",
        "done": t.done,
        "done_at": t.done_at,
        "due_at": t.due_at,
        "due_all_day": bool(t.due_at) and len(t.due_at or "") <= 10,
        "position": t.position,
    }


def _goal_tasks(db: Session, goal_id: str) -> list[GoalTask]:
    return (
        db.query(GoalTask)
        .join(GoalNode, GoalTask.node_id == GoalNode.id)
        .filter(GoalNode.goal_id == goal_id)
        .all()
    )


def _out(db: Session, goal: Goal) -> GoalOut:
    tasks = [task_dict(t) for t in _goal_tasks(db, goal.id)]
    done, total = tree.counts(tasks)
    return GoalOut(
        id=goal.id,
        title=goal.title,
        description=goal.description or "",
        archived=goal.archived,
        created_at=goal.created_at,
        updated_at=goal.updated_at,
        done_count=done,
        task_count=total,
        next_due_at=tree.next_due(tasks),
    )


def list_goals(db: Session, include_archived: bool = False) -> list[GoalOut]:
    q = db.query(Goal)
    if not include_archived:
        q = q.filter(Goal.archived.is_(False))
    return [_out(db, g) for g in q.order_by(Goal.created_at.desc()).all()]


def get_goal(db: Session, goal_id: str) -> GoalDetail | None:
    """One goal with its tree already nested, ordered and counted."""
    goal = db.get(Goal, goal_id)
    if goal is None:
        return None
    tasks_by_node: dict[str, list[dict[str, Any]]] = {}
    for t in _goal_tasks(db, goal_id):
        tasks_by_node.setdefault(t.node_id, []).append(task_dict(t))

    flat = []
    for n in db.query(GoalNode).filter(GoalNode.goal_id == goal_id).all():
        node_tasks = sorted(
            tasks_by_node.get(n.id, []), key=lambda t: (t["position"], t["title"])
        )
        done, total = tree.counts(node_tasks)
        flat.append(
            {
                "id": n.id,
                "goal_id": n.goal_id,
                "parent_id": n.parent_id,
                "title": n.title,
                "description": n.description or "",
                "position": n.position,
                "tasks": node_tasks,
                "done_count": done,
                "task_count": total,
            }
        )
    return GoalDetail(**_out(db, goal).model_dump(), nodes=tree.nest(flat))


def create_goal(db: Session, data: GoalCreate) -> GoalOut:
    now = now_iso()
    goal = Goal(
        id=str(uuid.uuid4()),
        title=data.title.strip(),
        description=data.description or "",
        created_at=now,
        updated_at=now,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return _out(db, goal)


def update_goal(db: Session, goal_id: str, data: GoalUpdate) -> GoalOut | None:
    goal = db.get(Goal, goal_id)
    if goal is None:
        return None
    if data.title is not None:
        goal.title = data.title.strip()
    if data.description is not None:
        goal.description = data.description
    if data.archived is not None:
        goal.archived = data.archived
    goal.updated_at = now_iso()
    db.commit()
    db.refresh(goal)
    return _out(db, goal)


def delete_goal(db: Session, goal_id: str) -> bool:
    goal = db.get(Goal, goal_id)
    if goal is None:
        return False
    db.delete(goal)  # nodes + their tasks cascade through the relationships
    db.commit()
    return True
