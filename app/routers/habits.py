from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.habit import Habit
from app.schemas.habit import HabitOut, HabitStats, HabitToggleResponse
from app.services import habits as svc

router = APIRouter(prefix="/api/habits", tags=["habits"])


@router.get("", response_model=list[HabitOut])
def get_habits(db: Session = Depends(get_db)):
    return svc.list_habits(db)


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
