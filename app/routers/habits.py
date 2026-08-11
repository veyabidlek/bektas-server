import re
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin, viewer_level, visible_levels
from app.models.habit import Habit
from app.schemas.habit import (
    HabitMarkResponse,
    HabitOut,
    HabitStats,
    HabitToggleResponse,
    HabitUpdate,
    MarkState,
)
from app.services import habits as svc

router = APIRouter(prefix="/api/habits", tags=["habits"])

_ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


class HabitCreate(BaseModel):
    id: str
    name: str
    emoji: str
    color: str
    visibility: str = "public"
    #: "education" / "health" / "islam" / … Blank is stored as NULL.
    category: str | None = None
    #: Daily goal for counted habits (Quran = 2). Omitted = plain tick-off.
    target_per_day: int | None = None


class VisibilityUpdate(BaseModel):
    visibility: str


class HabitMark(BaseModel):
    """One day, one state — or, for counted habits, one count.

    `MarkState` being a Literal is what turns a typo'd state into a 422 instead
    of a silently-stored value nothing knows how to read. When `amount` is
    given it wins: the state is derived from the count against the habit's
    daily goal, and the field's own value is ignored (the client sends "done"
    as a placeholder).
    """

    date: str
    state: MarkState
    amount: int | None = Field(default=None, ge=0, le=100_000)

    @field_validator("date")
    @classmethod
    def _iso_day(cls, value: str) -> str:
        # The stored key has to be byte-identical to the one every other read
        # builds with `date.isoformat()`, so the shape is checked before the
        # calendar is: `fromisoformat` would take "20260810" (3.11+) and
        # `strptime` would take "2026-8-10", and either would write a key that
        # nothing else can find. The regex pins the shape, strptime rejects
        # 2026-02-31.
        if not _ISO_DAY.fullmatch(value):
            raise ValueError("date must be YYYY-MM-DD")
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValueError("date must be a real calendar day")
        return value


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
        db,
        data.id,
        data.name,
        data.emoji,
        data.color,
        data.visibility,
        data.category,
        data.target_per_day,
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


# The three-state writer the swipe tracker uses. /toggle is left exactly as it
# was — it is the old boolean UI, and giving it a second meaning would change
# what every existing caller's tap does.
@router.post(
    "/{habit_id}/mark",
    response_model=HabitMarkResponse,
    # `amount` is None on every state-only write; excluding it keeps the
    # response byte-identical to what the swipe tracker has always received.
    response_model_exclude_none=True,
)
def mark_habit(
    habit_id: str,
    data: HabitMark,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    habit = db.query(Habit).filter(Habit.id == habit_id).first()
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")

    if data.amount is not None:
        state, amount = svc.set_day_amount(db, habit, data.date, data.amount)
        return HabitMarkResponse(date=data.date, state=state, amount=amount)

    state = svc.set_day_state(db, habit_id, data.date, data.state)
    return HabitMarkResponse(date=data.date, state=state)


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
