"""The assistant's snapshot, as text — the wording and the arithmetic, pure.

No database, no clock, no model. `assistant.py` fetches the rows and hands the
values here, the same split `weekly.py` / `week_stats.py` and `review.py` /
`review_score.py` already use, so every line the model reads is testable on its
own.

The shape matters more than it looks: the assistant is asked to be honest about
neglect, and it can only be honest about what it can *see*. So a habit carries
its last-7-days count rather than just today's tick, the task section carries
the size and age of the overdue pile, and focus time carries the week before it
to compare against. A number the context does not contain is a number the model
would have to invent.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta

#: How much of the open-task list the snapshot carries. Long enough to answer
#: "what's outstanding?", short enough that the prompt stays cheap.
TASK_LIMIT = 25

#: The adherence window. Seven days is what "this week" means to him in chat.
WEEK_DAYS = 7

EMPTY = "(none)"


def section(title: str, lines: Sequence[str], empty: str = EMPTY) -> str:
    """One labelled block. An empty section says so rather than vanishing —
    "no events tomorrow" is an answer, and a missing heading would read to the
    model as missing data it should hedge about."""
    body = [f"- {line}" for line in lines] or [f"- {empty}"]
    return "\n".join([title, *body])


def hhmm(iso: str | None) -> str | None:
    """The clock part of a stored timestamp, or None for an all-day shape.

    Everything in this database is stored with the Almaty offset already
    applied (`services/calendar.normalize_dt`), so these characters *are* his
    local time — no conversion, and none possible to get wrong.
    """
    return iso[11:16] if iso and len(iso) >= 16 else None


def days_between(later: str, earlier: str) -> int:
    """Whole days from `earlier` to `later`, both "YYYY-MM-DD"."""
    return (date.fromisoformat(later[:10]) - date.fromisoformat(earlier[:10])).days


def recent_days(today: str, count: int = WEEK_DAYS) -> list[str]:
    """The `count` days ending today, inclusive, oldest first."""
    last = date.fromisoformat(today[:10])
    return [(last - timedelta(days=n)).isoformat() for n in reversed(range(count))]


# --- events ---------------------------------------------------------------


def event_line(starts_at: str, title: str, all_day: bool = False) -> str:
    """"09:00 · Dentist", or "all-day · Eid"."""
    time = None if all_day else hhmm(starts_at)
    return f"{time} · {title}" if time else f"all-day · {title}"


# --- tasks ----------------------------------------------------------------


def task_line(title: str, due_at: str | None, today: str) -> str:
    """One open task, with lateness on the *left* where it cannot be skimmed past."""
    if not due_at:
        return f"{title} — no due date"

    day = due_at[:10]
    time = hhmm(due_at)
    when = f"{day} {time}" if time else day

    if day < today:
        return f"[OVERDUE {days_between(today, day)}d] {title} — due {when}"
    if day == today:
        return f"[TODAY] {title} — due {when}"
    return f"{title} — due {when}"


def _task_key(task, today: str) -> tuple:
    """Overdue first (oldest first), then today's, then dated, then undated."""
    day = (task.due_at or "")[:10]
    if not day:
        return (3, "", task.title)
    if day < today:
        return (0, day, task.title)
    if day == today:
        return (1, day, task.title)
    return (2, day, task.title)


def order_tasks(tasks: Sequence, today: str, limit: int = TASK_LIMIT) -> list:
    return sorted(tasks, key=lambda t: _task_key(t, today))[:limit]


def overdue_summary(tasks: Sequence, today: str) -> str:
    """"5 overdue, oldest 12 days: "fix landing"" — the pile's size and its age.

    The oldest one is named because "5 overdue" is a statistic and "fix landing,
    twelve days late" is a thing he can act on.
    """
    overdue = [t for t in tasks if t.due_at and t.due_at[:10] < today]
    if not overdue:
        return "none overdue"
    oldest = min(overdue, key=lambda t: t.due_at[:10])
    age = days_between(today, oldest.due_at)
    return f'{len(overdue)} overdue, oldest {age} days: "{oldest.title}"'


# --- habits ---------------------------------------------------------------


def week_done(completed_days: Mapping[str, object], days: Sequence[str]) -> int:
    # Truthy, not `is True`: a day's value is `True` or `"partial"`, and a day
    # he did some of the habit counts toward the week — the same call
    # review_score.py makes when it scores partial above missed.
    return sum(1 for day in days if completed_days.get(day))


def habit_line(
    name: str,
    category: str | None,
    done_today: bool,
    done_week: int,
    total: int = WEEK_DAYS,
) -> str:
    """"Quran [islam]: PENDING today · 2/7 days this week".

    Today's tick alone cannot tell a bad week from a slow morning — the count
    beside it is what lets an honest answer be specific instead of nagging.
    """
    label = f"{name} [{category}]" if category else name
    return f"{label}: {'done' if done_today else 'PENDING'} today · {done_week}/{total} days this week"


# --- focus time -----------------------------------------------------------


def minutes(total: int) -> str:
    """"0m" / "45m" / "3h 20m"."""
    if total < 60:
        return f"{total}m"
    hours, rest = divmod(total, 60)
    return f"{hours}h {rest}m" if rest else f"{hours}h"


def change_phrase(current: int, previous: int) -> str:
    """How this week compares — in words, so the model need not do the division."""
    if not previous:
        return "nothing the week before" if not current else "up from nothing the week before"
    if not current:
        return "down to nothing vs the week before"
    delta = round((current - previous) / previous * 100)
    if delta == 0:
        return "level with the week before"
    return f"{'up' if delta > 0 else 'down'} {abs(delta)}% vs the week before"


def focus_line(this_week: int, last_week: int) -> str:
    return (
        f"{minutes(this_week)} in the last 7 days, "
        f"{minutes(last_week)} the 7 before — {change_phrase(this_week, last_week)}"
    )


def sum_days(daily: dict[str, int], days: Sequence[str]) -> int:
    return sum(daily.get(day, 0) for day in days)


# --- sleep ----------------------------------------------------------------
# The band's numbers, worded. Same rule as the rest of this file: the model is
# handed the counts, never asked to infer them — "he is tired" is not something
# that can be read off a single night's total.

#: What a night is supposed to be. A week averaging under this is worth saying
#: out loud, unprompted; a single short night is not.
SLEEP_TARGET_MINUTES = 7 * 60


def hours_minutes(total: int) -> str:
    """"6h 40m" / "1h 05m" / "45m".

    Zero-padded, unlike `minutes()` above, which is left exactly as it is — the
    focus-time lines it writes are asserted character for character. Padding
    matters here because these numbers are read as clock durations beside one
    another, and "1h 5m" under "6h 40m" scans as five minutes of something.
    """
    if total < 60:
        return f"{total}m"
    hours, rest = divmod(total, 60)
    return f"{hours}h {rest:02d}m"


def sleep_line(
    date: str,
    asleep_minutes: int,
    deep_minutes: int | None,
    bedtime: str | None,
    wake_time: str | None,
) -> str:
    """"2026-08-11: 6h 40m asleep · 1h 05m deep · bed 00:12 → up 07:31".

    A `None` stage is **omitted**, never printed as zero: the band not
    reporting deep sleep and a night with no deep sleep are different facts,
    and only one of them is something to be told about.
    """
    parts = [f"{hours_minutes(asleep_minutes)} asleep"]
    if deep_minutes is not None:
        parts.append(f"{hours_minutes(deep_minutes)} deep")
    if bedtime and wake_time:
        parts.append(f"bed {hhmm(bedtime)} → up {hhmm(wake_time)}")
    return f"{date}: " + " · ".join(parts)


def sleep_average(minutes_per_night: Sequence[int]) -> int | None:
    """The mean over the nights that were *recorded*, or None for none.

    Nights the band missed are not counted as zero-sleep nights — that would
    turn a charger left plugged in over the weekend into an accusation.
    """
    if not minutes_per_night:
        return None
    return round(sum(minutes_per_night) / len(minutes_per_night))


def sleep_average_line(minutes_per_night: Sequence[int]) -> str:
    average = sleep_average(minutes_per_night)
    if average is None:
        return "no nights recorded"
    return f"{len(minutes_per_night)} night(s) recorded, averaging {hours_minutes(average)} asleep"


def sleep_shortfall(minutes_per_night: Sequence[int]) -> str | None:
    """The line that lets the assistant raise sleep on its own, or None.

    Only the average crosses the threshold, never one night — a single 4-hour
    night has a reason, a fortnight of them is a pattern.
    """
    average = sleep_average(minutes_per_night)
    if average is None or average >= SLEEP_TARGET_MINUTES:
        return None
    return (
        f"BELOW TARGET: averaging {hours_minutes(average)} over the last "
        f"{len(minutes_per_night)} nights, against a {hours_minutes(SLEEP_TARGET_MINUTES)} target"
    )


def goal_line(title: str, done: int, total: int, next_due: str | None, today: str) -> str:
    """One roadmap, with the number behind every claim it allows.

    Percent AND the raw counts: "60%" alone hides whether that is 3 of 5 or
    300 of 500, and the model would have to guess how much is left. A goal
    with no tasks yet says so rather than reading as 0% neglected — an empty
    plan is a plan not written, not a plan abandoned.
    """
    if total == 0:
        shape = "no tasks yet"
    else:
        shape = f"{round(done * 100 / total)}% ({done}/{total} tasks)"
    if not next_due:
        return f"{title} — {shape}, no deadline set"
    overdue = next_due[:10] < today
    when = "OVERDUE" if overdue else "next due"
    return f"{title} — {shape}, {when} {next_due[:10]}"
