"""Import a HabitKit export (JSON) into `habits` + `habit_completions`.

Run from the repository root, inside the app container so DATABASE_URL points
at the real database:

    python -m scripts.import_habitkit /path/to/habitkit_export.json

**Idempotent by habit id**: HabitKit UUIDs become our habit ids, and a habit
that already exists is skipped whole (with its completions), so a re-run after
a partial failure imports only what is missing. Nothing is updated or deleted.

Mapping decisions (2026-08-11, approved by Bektas over TG):
- `createdAt` (UTC) → our `created_at` as the **Almaty** date, the same clock
  every other date in this database lives on.
- The habit's interval supplies `target_per_day` when it is a per-day goal
  above 1 (`requiredNumberOfCompletionsPerDay`, type "day"/"none"). Week-type
  goals (Focus Time, Leetcode) have no equivalent here and import as plain
  habits — a weekly target mislabeled as daily would mark every day partial.
  With two intervals for one habit, the open one (endDate null, else latest
  startDate) wins.
- A completion's local day = its UTC instant + its own `timezoneOffsetInMinutes`
  — the offset HabitKit recorded at the tap, not today's zone.
- `amountOfCompletions` 0 means "ticked, no count" and imports as 1. Duplicate
  habit-day rows (a handful exist) keep the **max** amount — the counter is
  cumulative, so the larger number is the later state of the same day.
- state: at/above the daily goal → "done", below → "partial". `amount` is only
  stored on counted habits (goal > 1); a plain habit's tick stays the shape it
  always had.
- Categories via `categoryMappings`; a habit with two keeps the first by the
  mapping's own createdAt. Category NAMES import as-is ("Islam", "Prayers"…).
- HabitKit named colors → oklch in the palette's L/C neighbourhood; icons →
  emoji (the export's own emoji wins where set). Unknowns fall back visibly:
  📌 and the neutral gray.
- `isInverse` ("avoid" habits) has no equivalent; imported as normal habits.
"""

import json
import sys
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.models.habit import Habit, HabitCompletion
from app.services.habits import DONE, PARTIAL

# Tailwind-family names HabitKit uses → oklch in the L 0.72–0.79 / C 0.15 band
# the existing palette sits in (muted grays keep a whisper of chroma).
COLOR_MAP = {
    "red": "oklch(0.72 0.15 25)",
    "orange": "oklch(0.75 0.15 55)",
    "amber": "oklch(0.78 0.15 75)",
    "yellow": "oklch(0.79 0.15 95)",
    "lime": "oklch(0.76 0.15 125)",
    "green": "oklch(0.74 0.15 145)",
    "emerald": "oklch(0.74 0.15 160)",
    "teal": "oklch(0.74 0.14 180)",
    "sky": "oklch(0.74 0.14 220)",
    "blue": "oklch(0.72 0.15 245)",
    "indigo": "oklch(0.72 0.15 275)",
    "purple": "oklch(0.72 0.15 300)",
    "pink": "oklch(0.74 0.15 340)",
    "rose": "oklch(0.73 0.15 15)",
    "slate": "oklch(0.74 0.03 240)",
    "stone": "oklch(0.75 0.03 60)",
    "neutral": "oklch(0.75 0.02 90)",
}
FALLBACK_COLOR = "oklch(0.75 0.02 90)"

ICON_EMOJI = {
    "alarm_check": "⏰", "treadmill": "🏃", "rocket": "🚀", "dollar_sign": "💵",
    "code": "💻", "terminal": "💻", "fire": "🔥", "smartphoneSlash": "📵",
    "coins": "🪙", "glass": "🥛", "swimming": "🏊", "bed": "🛏️",
    "utensils": "🍽️", "leaf": "🍃", "makeMusic": "🎵", "book": "📖",
    "bookSpine": "📚", "podcast": "🎧", "edit": "✍️", "writing": "✍️",
    "cloud_moon": "🌙", "moon": "🌙", "activity": "💪", "dumbbell": "🏋️",
    "bike": "🚴", "palette": "🎨",
}
FALLBACK_EMOJI = "📌"

ALMATY_OFFSET = timedelta(minutes=300)


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def habit_created_date(created_at_utc: str) -> str:
    return (parse_utc(created_at_utc) + ALMATY_OFFSET).date().isoformat()


def completion_local_date(completion: dict) -> str:
    offset = timedelta(minutes=completion.get("timezoneOffsetInMinutes") or 0)
    return (parse_utc(completion["date"]) + offset).date().isoformat()


def pick_interval(intervals: list[dict]) -> dict | None:
    if not intervals:
        return None
    open_ones = [i for i in intervals if i.get("endDate") is None]
    pool = open_ones or intervals
    return max(pool, key=lambda i: i.get("startDate") or "")


def target_from_interval(interval: dict | None) -> int | None:
    if not interval:
        return None
    if interval.get("type") == "week":
        return None
    per_day = interval.get("requiredNumberOfCompletionsPerDay") or 1
    return per_day if per_day > 1 else None


def emoji_for(habit: dict) -> str:
    if habit.get("emoji"):
        return habit["emoji"]
    return ICON_EMOJI.get(habit.get("icon") or "", FALLBACK_EMOJI)


def category_for(habit_id: str, mappings: list[dict], categories: dict[str, str]) -> str | None:
    mine = sorted(
        (m for m in mappings if m["habitId"] == habit_id),
        key=lambda m: m.get("createdAt") or "",
    )
    for m in mine:
        name = categories.get(m["categoryId"])
        if name:
            return name
    return None


def day_rows(completions: list[dict], target: int | None) -> dict[str, tuple[str, int | None]]:
    """(state, stored-amount) per local day, duplicates folded to max amount."""
    per_day: dict[str, int] = {}
    for c in completions:
        day = completion_local_date(c)
        amount = max(c.get("amountOfCompletions") or 0, 1)
        per_day[day] = max(per_day.get(day, 0), amount)

    goal = target or 1
    rows: dict[str, tuple[str, int | None]] = {}
    for day, amount in per_day.items():
        state = DONE if amount >= goal else PARTIAL
        rows[day] = (state, amount if target else None)
    return rows


def import_export(db, data: dict) -> None:
    categories = {c["id"]: c["name"] for c in data.get("categories", [])}
    mappings = data.get("categoryMappings", [])
    by_habit: dict[str, list[dict]] = {}
    for c in data.get("completions", []):
        by_habit.setdefault(c["habitId"], []).append(c)
    intervals_by_habit: dict[str, list[dict]] = {}
    for i in data.get("intervals", []):
        intervals_by_habit.setdefault(i["habitId"], []).append(i)

    imported = skipped = completion_count = 0
    for h in data.get("habits", []):
        if db.query(Habit).filter(Habit.id == h["id"]).first():
            skipped += 1
            continue
        target = target_from_interval(pick_interval(intervals_by_habit.get(h["id"], [])))
        db.add(
            Habit(
                id=h["id"],
                name=h["name"].strip(),
                emoji=emoji_for(h),
                color=COLOR_MAP.get(h.get("color") or "", FALLBACK_COLOR),
                archived=bool(h.get("archived")),
                visibility="public",
                category=category_for(h["id"], mappings, categories),
                created_at=habit_created_date(h["createdAt"]),
                target_per_day=target,
            )
        )
        for day, (state, amount) in day_rows(by_habit.get(h["id"], []), target).items():
            db.add(
                HabitCompletion(habit_id=h["id"], date=day, state=state, amount=amount)
            )
            completion_count += 1
        imported += 1

    db.commit()
    print(f"imported {imported} habits ({completion_count} day rows), skipped {skipped} already present")


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python -m scripts.import_habitkit <habitkit_export.json>")
    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)
    db = SessionLocal()
    try:
        import_export(db, data)
    finally:
        db.close()


if __name__ == "__main__":
    main()
