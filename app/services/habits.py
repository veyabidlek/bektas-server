from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.habit import Habit, HabitCompletion
from app.schemas.habit import HabitOut, HabitStats


def list_habits(db: Session) -> list[HabitOut]:
    habits = db.query(Habit).all()
    result = []

    for habit in habits:
        completions = (
            db.query(HabitCompletion.date)
            .filter(HabitCompletion.habit_id == habit.id)
            .all()
        )
        completed_days = {c.date: True for c in completions}
        result.append(
            HabitOut(
                id=habit.id,
                name=habit.name,
                emoji=habit.emoji,
                color=habit.color,
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

    # Current streak: walk backwards from today
    current_streak = 0
    for i in range(days):
        d = (today - timedelta(days=i)).isoformat()
        if d in completed_set:
            current_streak += 1
        elif i == 0:
            continue  # today might not be done yet
        else:
            break

    return HabitStats(
        completed=len(completed_set),
        total=days,
        current_streak=current_streak,
    )
