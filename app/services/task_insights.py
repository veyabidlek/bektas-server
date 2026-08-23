"""What the board actually says, as numbers — no database, no model.

The same bargain `assistant.py` makes and for the same reason: a claim the
assistant should be able to make needs the number behind it computed first. A
model handed a raw task list and asked "how am I doing?" will guess, and it
will guess encouragingly.

So the arithmetic is here, it is pure, and the model's job is only to say it
in a sentence. When there is no model the numbers are still shown — the
analysis degrades to a table, not to nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.task import TaskOut

#: An In Progress card older than this has stopped being "in progress" and
#: started being a thing he is avoiding. Two weeks is long enough not to nag
#: about a task he picked up on Friday.
STALE_DAYS = 14

#: How many titles to name. A list long enough to scroll is not a summary.
NAMED = 5


@dataclass
class BoardInsights:
    """Everything the analysis is allowed to claim."""

    today: str
    todo: int = 0
    in_progress: int = 0
    done: int = 0
    #: Open, dated, and the date has passed.
    overdue: int = 0
    #: Open and never placed in the matrix.
    unsorted: int = 0
    #: Open, urgent AND important.
    do_first: int = 0
    #: In Progress and not touched for STALE_DAYS.
    stalled: int = 0
    #: Open with no due date at all — invisible to the calendar and the brief.
    undated: int = 0
    overdue_titles: list[str] = field(default_factory=list)
    stalled_titles: list[str] = field(default_factory=list)
    do_first_titles: list[str] = field(default_factory=list)


def _day(value: str | None) -> str | None:
    """The date half of either due-date shape."""
    return value[:10] if value else None


def _days_between(earlier: str, later: str) -> int:
    """Whole days between two "YYYY-MM-DD" prefixes.

    Deliberately string arithmetic via `date.fromisoformat` on the first ten
    characters rather than parsing the offsets: both shapes the app stores
    ("2026-08-20" and "2026-08-20T14:30:00+05:00") answer the same question
    here, and nothing about staleness needs an hour.
    """
    from datetime import date

    try:
        return (date.fromisoformat(later[:10]) - date.fromisoformat(earlier[:10])).days
    except ValueError:
        return 0


def summarize(tasks: list[TaskOut], today: str) -> BoardInsights:
    """The board, counted. `tasks` is the ACTIVE set — archived is the caller's
    business, and an archived task is one he has decided not to do."""
    out = BoardInsights(today=today)

    for task in tasks:
        if task.status == "done":
            out.done += 1
            # A finished task cannot be overdue, stalled or worth triaging, so
            # nothing below applies to it.
            continue

        if task.status == "in_progress":
            out.in_progress += 1
            if _days_between(task.updated_at, today) >= STALE_DAYS:
                out.stalled += 1
                if len(out.stalled_titles) < NAMED:
                    out.stalled_titles.append(task.title)
        else:
            out.todo += 1

        due = _day(task.due_at)
        if due is None:
            out.undated += 1
        elif due < today:
            out.overdue += 1
            if len(out.overdue_titles) < NAMED:
                out.overdue_titles.append(task.title)

        if task.quadrant == "unsorted":
            out.unsorted += 1
        elif task.quadrant == "do_first":
            out.do_first += 1
            if len(out.do_first_titles) < NAMED:
                out.do_first_titles.append(task.title)

    return out


def as_context(insights: BoardInsights) -> str:
    """The numbers, worded for the model.

    Every line is a fact from `summarize`. The model is told these and nothing
    else about the board, which is what stops it inventing a trend.
    """
    lines = [
        f"Today is {insights.today}.",
        f"To Do: {insights.todo}. In Progress: {insights.in_progress}. "
        f"Completed: {insights.done}.",
        f"Overdue: {insights.overdue}. Undated open tasks: {insights.undated}.",
        f"Never placed in the Eisenhower matrix: {insights.unsorted}.",
        f"Urgent and important right now: {insights.do_first}.",
        f"In Progress and untouched for {STALE_DAYS}+ days: {insights.stalled}.",
    ]
    for label, titles in (
        ("Overdue", insights.overdue_titles),
        ("Stalled", insights.stalled_titles),
        ("Do First", insights.do_first_titles),
    ):
        if titles:
            lines.append(f"{label}: {'; '.join(titles)}")
    return "\n".join(lines)
