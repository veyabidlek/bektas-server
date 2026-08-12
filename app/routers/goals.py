from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.models.goal import Goal
from app.schemas.goal import (
    AiDraftOut,
    AiDraftRequest,
    AiTasksOut,
    GoalCreate,
    GoalDetail,
    GoalNodeCreate,
    GoalNodeOut,
    GoalNodeUpdate,
    GoalOut,
    GoalTaskCreate,
    GoalTaskOut,
    GoalTaskUpdate,
    GoalUpdate,
)
from app.services import goal_items, goals, goals_ai

router = APIRouter(prefix="/api/goals", tags=["goals"])

#: Said out loud rather than as a 500, exactly like the assistant's: the
#: feature is not broken, there is simply no model to draft with.
AI_UNAVAILABLE = (
    "Drafting is unavailable — DEEPSEEK_API_KEY is not configured, "
    "or the model did not return a usable roadmap."
)


def _node_out(node) -> GoalNodeOut:
    """A freshly written node: no children yet, no tasks yet."""
    return GoalNodeOut(
        id=node.id,
        goal_id=node.goal_id,
        parent_id=node.parent_id,
        title=node.title,
        description=node.description or "",
        position=node.position,
        tasks=[],
        children=[],
        done_count=0,
        task_count=0,
    )


@router.get("", response_model=list[GoalOut])
def list_goals(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    return goals.list_goals(db, include_archived)


@router.post("", response_model=GoalOut, status_code=201)
def create_goal(
    data: GoalCreate, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    if not data.title.strip():
        raise HTTPException(status_code=422, detail="A goal needs a title")
    return goals.create_goal(db, data)


@router.get("/{goal_id}", response_model=GoalDetail)
def get_goal(goal_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    goal = goals.get_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.patch("/{goal_id}", response_model=GoalOut)
def update_goal(
    goal_id: str,
    data: GoalUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    goal = goals.update_goal(db, goal_id, data)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.delete("/{goal_id}", status_code=204)
def delete_goal(goal_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    if not goals.delete_goal(db, goal_id):
        raise HTTPException(status_code=404, detail="Goal not found")


@router.post("/{goal_id}/nodes", response_model=GoalNodeOut, status_code=201)
def add_node(
    goal_id: str,
    data: GoalNodeCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if not data.title.strip():
        raise HTTPException(status_code=422, detail="A node needs a title")
    node = goal_items.add_node(db, goal_id, data)
    if node is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return _node_out(node)


@router.patch("/nodes/{node_id}", response_model=GoalNodeOut)
def update_node(
    node_id: str,
    data: GoalNodeUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    node = goal_items.update_node(db, node_id, data)
    if node is None:
        # Either it is gone, or the move would have made it its own ancestor.
        raise HTTPException(status_code=404, detail="Node not found, or that move is a cycle")
    return _node_out(node)


@router.delete("/nodes/{node_id}", status_code=204)
def delete_node(node_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    if not goal_items.delete_node(db, node_id):
        raise HTTPException(status_code=404, detail="Node not found")


@router.post("/nodes/{node_id}/tasks", response_model=GoalTaskOut, status_code=201)
def add_task(
    node_id: str,
    data: GoalTaskCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if not data.title.strip():
        raise HTTPException(status_code=422, detail="A task needs a title")
    task = goal_items.add_task(db, node_id, data)
    if task is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return GoalTaskOut(**goals.task_dict(task))


@router.patch("/tasks/{task_id}", response_model=GoalTaskOut)
def update_task(
    task_id: str,
    data: GoalTaskUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    task = goal_items.update_task(db, task_id, data)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return GoalTaskOut(**goals.task_dict(task))


@router.post("/tasks/{task_id}/toggle", response_model=GoalTaskOut)
def toggle_task(task_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    task = goal_items.toggle_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return GoalTaskOut(**goals.task_dict(task))


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    if not goal_items.delete_task(db, task_id):
        raise HTTPException(status_code=404, detail="Task not found")


@router.post("/ai/draft", response_model=AiDraftOut)
def ai_draft(
    data: AiDraftRequest,
    _: None = Depends(require_admin),
):
    """A proposed tree for a goal. Nothing is saved — he confirms first."""
    goal = data.goal.strip()
    if not goal:
        raise HTTPException(status_code=422, detail="Say what the goal is")
    nodes = goals_ai.draft_roadmap(goal)
    if nodes is None:
        raise HTTPException(status_code=503, detail=AI_UNAVAILABLE)
    return AiDraftOut(nodes=nodes)


@router.post("/nodes/{node_id}/ai/tasks", response_model=AiTasksOut)
def ai_tasks(
    node_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Suggested next actions for one node. Also a proposal, not a write."""
    from app.models.goal import GoalNode  # local: only this route needs it

    node = db.get(GoalNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    goal = db.get(Goal, node.goal_id)
    tasks = goals_ai.suggest_tasks(node.title, goal.title if goal else "", node.description or "")
    if tasks is None:
        raise HTTPException(status_code=503, detail=AI_UNAVAILABLE)
    return AiTasksOut(tasks=tasks)
