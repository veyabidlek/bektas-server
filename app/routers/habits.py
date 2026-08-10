from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin, viewer_level, visible_levels
from app.models.habit import Habit
from app.schemas.habit import HabitOut, HabitStats, HabitToggleResponse, HabitUpdate
from app.services import habits as svc

router = APIRouter(prefix="/api/habits", tags=["habits"])


class HabitCreate(BaseModel):
    id: str
    name: str
    emoji: str
    color: str
    visibility: str = "public"
    #: "education" / "health" / "islam" / … Blank is stored as NULL.
    category: str | None = None


class VisibilityUpdate(BaseModel):
    visibility: str


@router.get("", response_model=list[HabitOut])
def get_habits(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    level: str = Depends(viewer_level),
):
    return svc.list_habits(
        db, include_archived=include_archived, levels=visible_levels(level)
    )


@router.post("", response_model=HabitOut, status_code=201)
def create_habit(
    data: HabitCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    existing = db.query(Habit).filter(Habit.id == data.id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Habit already exists")
    return svc.create_habit(
        db, data.id, data.name, data.emoji, data.color, data.visibility, data.category
    )


@router.patch("/{habit_id}", response_model=HabitOut)
def update_habit(
    habit_id: str,
    data: HabitUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Edit a habit in place. Sending `category: ""` clears it back to ungrouped."""
    if not svc.update_habit(db, habit_id, data):
        raise HTTPException(status_code=404, detail="Habit not found")
    habits = svc.list_habits(db, include_archived=True)
    return next(h for h in habits if h.id == habit_id)


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


@router.patch("/{habit_id}/visibility", response_model=HabitOut)
def set_visibility(
    habit_id: str,
    data: VisibilityUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if data.visibility not in ("public", "friends", "private"):
        raise HTTPException(status_code=422, detail="Invalid visibility")
    if not svc.set_visibility(db, habit_id, data.visibility):
        raise HTTPException(status_code=404, detail="Habit not found")
    habits = svc.list_habits(db, include_archived=True)
    return next(h for h in habits if h.id == habit_id)


# Admin-only: this writes to Bektas's own tracker, it is not a public action.
@router.post("/{habit_id}/toggle", response_model=HabitToggleResponse)
def toggle_habit(
    habit_id: str,
    target_date: str | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
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
    level: str = Depends(viewer_level),
):
    habit = db.query(Habit).filter(Habit.id == habit_id).first()
    if not habit or habit.visibility not in visible_levels(level):
        raise HTTPException(status_code=404, detail="Habit not found")
    return svc.get_habit_stats(db, habit_id, days)
