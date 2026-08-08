"""The score math, on its own.

Bektas plans his day in the calendar — "07:00 wake up" — and wants to know
whether it happened. Each of the day's events gets one answer in the evening,
and the answers become a percentage.

Pure: no clock, no database, no Telegram. Everything that fetches events lives
in `review.py` and hands its answers to `summarize()`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

OUTCOMES = ("done", "partial", "no")

# A half credit for "partly": it is the honest answer for a 07:00 alarm that
# won at 07:20, and refusing to score it would push every such day to 0.
WEIGHTS = {"done": 1.0, "partial": 0.5, "no": 0.0}


@dataclass(frozen=True)
class DayScore:
    day: str
    #: Events on the day — the denominator of "4/6".
    total: int
    #: Events that have been answered. Unanswered ones do not count against him.
    reviewed: int
    done: int
    partial: int
    no: int
    #: 0-100, or None when nothing has been answered yet.
    percent: int | None

    @property
    def has_data(self) -> bool:
        return self.percent is not None


def summarize(day: str, total: int, outcomes: Sequence[str]) -> DayScore:
    """The score of a day. done = 1, partly = ½, no = 0, over *reviewed* events."""
    counts = {name: 0 for name in OUTCOMES}
    for outcome in outcomes:
        if outcome in counts:
            counts[outcome] += 1

    reviewed = sum(counts.values())
    earned = sum(WEIGHTS[name] * count for name, count in counts.items())
    percent = round(earned / reviewed * 100) if reviewed else None

    return DayScore(
        day=day,
        total=total,
        reviewed=reviewed,
        done=counts["done"],
        partial=counts["partial"],
        no=counts["no"],
        percent=percent,
    )
