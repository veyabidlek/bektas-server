"""The week's arithmetic, on its own.

The weekly digest goes out on a Sunday evening, so "the week" has to mean the
same seven days to the bot, to the site and to the tests. Here that is settled
once: **Monday-based, Asia/Almaty, Sunday inclusive** — the week a Sunday
evening belongs to is the one that is ending, not the one about to start.

Pure: no clock of its own, no database, no Telegram. `weekly.py` fetches the
rows and hands the counts here, exactly the way `review.py` hands its answers
to `review_score.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.services.review_score import DayScore

#: A day at or above this counts as a filled bar in the strip — the same
#: threshold the site draws with (`components/calendar/review.ts`). One rule,
#: two surfaces.
GOOD_DAY = 60

FULL = "▮"
EMPTY = "▯"


@dataclass(frozen=True)
class Week:
    """Seven days, Monday first."""

    start: str  #: Monday, YYYY-MM-DD
    end: str  #: Sunday, YYYY-MM-DD, inclusive

    @property
    def days(self) -> list[str]:
        first = datetime.fromisoformat(self.start)
        return [(first + timedelta(days=n)).strftime("%Y-%m-%d") for n in range(7)]

    @property
    def after(self) -> str:
        """The Monday after this week — the exclusive upper bound for a query."""
        return (datetime.fromisoformat(self.end) + timedelta(days=1)).strftime("%Y-%m-%d")


def week_of(day: str) -> Week:
    """The Monday-based week containing `day` ("YYYY-MM-DD")."""
    date = datetime.fromisoformat(day[:10])
    monday = date - timedelta(days=date.weekday())
    return Week(
        start=monday.strftime("%Y-%m-%d"),
        end=(monday + timedelta(days=6)).strftime("%Y-%m-%d"),
    )


def week_containing(now: datetime) -> Week:
    return week_of(now.strftime("%Y-%m-%d"))


def next_week(week: Week) -> Week:
    return week_of(week.after)


def bar(percent: int | None) -> str:
    """One day of the strip. A day he never reviewed is unknown, not a zero."""
    return FULL if percent is not None and percent >= GOOD_DAY else EMPTY


def strip(scores: Sequence[DayScore]) -> str:
    """"▮▮▯▮▮▯▯" — the dashboard's mini strip, as text."""
    return "".join(bar(score.percent) for score in scores)


def average(scores: Sequence[DayScore]) -> int | None:
    """The week's effectiveness: the mean of the days actually reviewed.

    A week he forgot to review must not read as a week he failed, so unreviewed
    days are left out rather than counted as nought.
    """
    scored = [s.percent for s in scores if s.percent is not None]
    if not scored:
        return None
    return round(sum(scored) / len(scored))


@dataclass(frozen=True)
class WeekStats:
    """Everything the digest's first section says, already counted."""

    week: Week
    events: int
    #: 0-100, or None when no day of the week was reviewed.
    effectiveness: int | None
    strip: str
    tasks_done: int
    tasks_added: int
    diary_days: int
    inbox_captured: int
    inbox_triaged: int

    @property
    def is_empty(self) -> bool:
        """A week with nothing recorded at all — worth saying plainly."""
        return not (
            self.events
            or self.tasks_done
            or self.tasks_added
            or self.diary_days
            or self.inbox_captured
        )


def summarize_week(
    week: Week,
    scores: Sequence[DayScore],
    *,
    tasks_done: int,
    tasks_added: int,
    diary_days: int,
    inbox_captured: int,
    inbox_triaged: int,
) -> WeekStats:
    """`scores` is the week's seven days, Monday first."""
    return WeekStats(
        week=week,
        events=sum(score.total for score in scores),
        effectiveness=average(scores),
        strip=strip(scores),
        tasks_done=tasks_done,
        tasks_added=tasks_added,
        diary_days=diary_days,
        inbox_captured=inbox_captured,
        inbox_triaged=inbox_triaged,
    )
