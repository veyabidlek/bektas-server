from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.habit import Habit, HabitCompletion
from app.schemas.habit import DayState, HabitOut, HabitStats, HabitUpdate

#: Stored on a completion row. "done" is the historical meaning of "a row exists".
DONE = "done"
PARTIAL = "partial"
#: Asked for over the API only — it is stored as the absence of a row.
NONE = "none"


def day_value(state: str) -> DayState:
    """What a stored completion looks like in `completed_days`.

    "done" becomes `True`, not the string, because that map was a
    `{date: true}` before partial existed and clients truthy-check it. Widening
    the value domain is only safe as long as the old value keeps its old shape.
    """
    return True if state == DONE else state  # type: ignore[return-value]


def normalize_category(value: str | None) -> str | None:
    """Trim it; blank means ungrouped.

    Pure, and the single place the rule lives — an empty box in the UI and a
    missing field have to mean the same thing, or the list grows a "" group
    nobody asked for.
    """
    if value is None:
        return None
    return value.strip() or None


def create_habit(
    db: Session,
    habit_id: str,
    name: str,
    emoji: str,
    color: str,
    visibility: str = "public",
    category: str | None = None,
) -> HabitOut:
    habit = Habit(
        id=habit_id,
        name=name,
        emoji=emoji,
        color=color,
        archived=False,
        visibility=visibility,
        category=normalize_category(category),
    )
    db.add(habit)
    db.commit()
    return HabitOut(
        id=habit.id,
        name=habit.name,
        emoji=habit.emoji,
        color=habit.color,
        archived=False,
        visibility=habit.visibility,
        category=habit.category,
        completed_days={},
    )


def update_habit(db: Session, habit_id: str, data: HabitUpdate) -> bool:
    """Write the fields the request actually carried. False = no such habit."""
    habit = db.query(Habit).filter(Habit.id == habit_id).first()
    if not habit:
        return False

    fields = data.model_dump(exclude_unset=True)
    if "category" in fields:
        fields["category"] = normalize_category(fields["category"])
    for field, value in fields.items():
        if value is None and field != "category":
            continue  # only the category is clearable
        setattr(habit, field, value.strip() if isinstance(value, str) else value)

    db.commit()
    return True


def set_visibility(db: Session, habit_id: str, visibility: str) -> bool:
    habit = db.query(Habit).filter(Habit.id == habit_id).first()
    if not habit:
        return False
    habit.visibility = visibility
    db.commit()
    return True


def archive_habit(db: Session, habit_id: str, archived: bool) -> bool:
    habit = db.query(Habit).filter(Habit.id == habit_id).first()
    if not habit:
        return False
    habit.archived = archived
    db.commit()
    return True


def list_habits(
    db: Session,
    include_archived: bool = False,
    levels: list[str] | None = None,
) -> list[HabitOut]:
    q = db.query(Habit)
    if not include_archived:
        q = q.filter(Habit.archived == False)  # noqa: E712
    if levels is not None:
        q = q.filter(Habit.visibility.in_(levels))
    habits = q.all()
    result = []

    for habit in habits:
        completions = (
            db.query(HabitCompletion.date, HabitCompletion.state)
            .filter(HabitCompletion.habit_id == habit.id)
            .all()
        )
        completed_days = {c.date: day_value(c.state) for c in completions}
        result.append(
            HabitOut(
                id=habit.id,
                name=habit.name,
                emoji=habit.emoji,
                color=habit.color,
                archived=habit.archived,
                visibility=habit.visibility,
                category=habit.category,
                completed_days=completed_days,
            )
        )

    return result


def toggle_habit(db: Session, habit_id: str, target_date: str) -> bool:
    existing = (
        db.query(HabitCompletion)
        .filter(
            HabitCompletion.habit_id == habit_id,
            HabitCompletion.date == target_date,
        )
        .first()
    )

    if existing:
        db.delete(existing)
        db.commit()
        return False

    completion = HabitCompletion(habit_id=habit_id, date=target_date)
    db.add(completion)
    db.commit()
    return True


def set_day_state(db: Session, habit_id: str, target_date: str, state: str) -> str:
    """Put one day into one of the three states. Returns the state now in force.

    Unlike `toggle_habit` this is not a flip — the caller says what it wants, so
    a swipe that lands on "partial" twice is idempotent instead of undoing
    itself. `toggle_habit` stays as it was for the old boolean UI; it will
    happily delete a partial day, which is the honest meaning of un-ticking it.

    "none" deletes the row rather than storing a third value: everything that
    reads a habit — stats, streaks, the assistant's context — already spells
    "not done" as "no row", and a stored "none" would have to be filtered out
    of every one of them.
    """
    existing = (
        db.query(HabitCompletion)
        .filter(
            HabitCompletion.habit_id == habit_id,
            HabitCompletion.date == target_date,
        )
        .first()
    )

    if state == NONE:
        if existing:
            db.delete(existing)
            db.commit()
        return NONE

    if existing:
        existing.state = state
    else:
        db.add(HabitCompletion(habit_id=habit_id, date=target_date, state=state))
    db.commit()
    return state


def get_habit_stats(db: Session, habit_id: str, days: int = 30) -> HabitStats:
    today = date.today()
    start = today - timedelta(days=days - 1)
    start_str = start.isoformat()

    completions = (
        db.query(HabitCompletion.date)
        .filter(
            HabitCompletion.habit_id == habit_id,
            HabitCompletion.date >= start_str,
        )
        .all()
    )
    completed_set = {c.date for c in completions}

    current_streak = 0
    for i in range(days):
        d = (today - timedelta(days=i)).isoformat()
        if d in completed_set:
            current_streak += 1
        elif i == 0:
            continue
        else:
            break

    return HabitStats(
        completed=len(completed_set),
        total=days,
        current_streak=current_streak,
    )
