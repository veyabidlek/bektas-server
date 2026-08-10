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
