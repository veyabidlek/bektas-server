from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.models.habit import Habit
from app.schemas.habit import HabitOut, HabitStats, HabitToggleResponse
from app.services import habits as svc

router = APIRouter(prefix="/api/habits", tags=["habits"])


class HabitCreate(BaseModel):
    id: str
    name: str
    emoji: str
    color: str


@router.get("", response_model=list[HabitOut])
def get_habits(
    include_archived: bool = False,
    db: Session = Depends(get_db),
):
    return svc.list_habits(db, include_archived=include_archived)


@router.post("", response_model=HabitOut, status_code=201)
def create_habit(
    data: HabitCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    existing = db.query(Habit).filter(Habit.id == data.id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Habit already exists")
    return svc.create_habit(db, data.id, data.name, data.emoji, data.color)


@router.patch("/{habit_id}/archive")
def toggle_archive(
    habit_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    habit = db.query(Habit).filter(Habit.id == habit_id).first()
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")
    svc.archive_habit(db, habit_id, not habit.archived)
    return {"id": habit_id, "archived": not habit.archived}


@router.post("/{habit_id}/toggle", response_model=HabitToggleResponse)
def toggle_habit(
    habit_id: str,
    target_date: str | None = None,
    db: Session = Depends(get_db),
):
    habit = db.query(Habit).filter(Habit.id == habit_id).first()
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")

    d = target_date or date.today().isoformat()
    completed = svc.toggle_habit(db, habit_id, d)
    return HabitToggleResponse(date=d, completed=completed)


@router.get("/{habit_id}/stats", response_model=HabitStats)
def get_habit_stats(
    habit_id: str,
    days: int = 30,
    db: Session = Depends(get_db),
):
    habit = db.query(Habit).filter(Habit.id == habit_id).first()
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")
    return svc.get_habit_stats(db, habit_id, days)
