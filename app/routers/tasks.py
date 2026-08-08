from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.schemas.task import (
    TaskCreate,
    TaskDoneUpdate,
    TaskOut,
    TaskTodaySummary,
    TaskUpdate,
)
from app.services import tasks as svc

# Admin-only, like the calendar and the diary.
router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/today", response_model=TaskTodaySummary)
def get_today(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    """Declared before /{task_id} routes so "today" is never read as an id."""
    return svc.today_summary(db)


@router.get("", response_model=list[TaskOut])
def list_tasks(
    include_done: bool = True,
    start: str | None = None,
    end: str | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    return svc.list_tasks(db, include_done=include_done, start=start, end=end)


@router.post("", response_model=TaskOut, status_code=201)
def create_task(
    data: TaskCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if not data.title.strip():
        raise HTTPException(status_code=422, detail="Title is required")
    try:
        task = svc.create_task(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return svc.out(task)


@router.put("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: str,
    data: TaskUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    task = svc.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        task = svc.update_task(db, task, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return svc.out(task)


@router.patch("/{task_id}/done", response_model=TaskOut)
def set_done(
    task_id: str,
    data: TaskDoneUpdate | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Tick or untick. With no body it toggles — that is what the checkbox sends."""
    task = svc.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return svc.out(svc.set_done(db, task, data.done if data else None))


@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    task = svc.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    svc.delete_task(db, task)
