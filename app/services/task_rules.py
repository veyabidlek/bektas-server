"""What a task's status and priority MEAN — no database, no HTTP.

Same split as `assistant.py` / `assistant_format.py` and `sleep.py` /
`sleep_night.py`: the arithmetic and the vocabulary live here, where they are
tested without a session, and `tasks.py` does the writing.

Two ideas, kept apart on purpose:

* **Status** is where the work is — todo, in progress, done. One axis, three
  values, and the board's three columns are exactly those values.
* **Priority** is the Eisenhower matrix: urgent and important are two
  independent booleans, and the quadrant is *derived* from them. There is no
  stored quadrant, so a quadrant can never disagree with the checkboxes that
  produced it.
"""
from __future__ import annotations

TODO = "todo"
IN_PROGRESS = "in_progress"
DONE = "done"

#: The board's columns, in the order they are drawn.
STATUSES: tuple[str, ...] = (TODO, IN_PROGRESS, DONE)

#: The four quadrants, plus the one the matrix cannot avoid having.
DO_FIRST = "do_first"
SCHEDULE = "schedule"
DELEGATE = "delegate"
ELIMINATE = "eliminate"
#: ⚠️ Not a fifth quadrant — the ABSENCE of an answer. `urgent`/`important` are
#: nullable because every task that existed before the matrix did has never
#: been asked the question, and defaulting them to (not urgent, not important)
#: would file Bektas's whole backlog under "Eliminate", which is a claim the
#: data does not support. A new task starts here too: the matrix is a decision,
#: and pretending it was already made is what makes people stop trusting it.
UNSORTED = "unsorted"

_QUADRANTS: dict[tuple[bool, bool], str] = {
    (True, True): DO_FIRST,
    (False, True): SCHEDULE,
    (True, False): DELEGATE,
    (False, False): ELIMINATE,
}

#: Sort order for "by priority" — most pressing first, undecided last. Not the
#: same thing as the drawing order of the matrix, which is a 2×2 grid and has
#: no single sequence.
_PRIORITY_RANK: dict[str, int] = {
    DO_FIRST: 0,
    SCHEDULE: 1,
    DELEGATE: 2,
    ELIMINATE: 3,
    UNSORTED: 4,
}

#: Sort order for "by status" — the board read left to right.
_STATUS_RANK: dict[str, int] = {status: i for i, status in enumerate(STATUSES)}


def normalize_status(value: str | None) -> str:
    """A status string as it will be stored, or ValueError.

    Liberal about shape (case, spaces, the hyphen someone will inevitably type
    instead of the underscore), strict about the set. The router turns the
    ValueError into a 422 that names what was sent.
    """
    if value is None:
        raise ValueError("status is required")
    cleaned = value.strip().lower().replace("-", "_").replace(" ", "_")
    if cleaned not in _STATUS_RANK:
        raise ValueError(f"unknown status {value!r} — expected one of {', '.join(STATUSES)}")
    return cleaned


def is_done(status: str) -> bool:
    """The one place "finished" is defined.

    `tasks.done` is a denormalized copy of this answer (see `tasks._apply_status`),
    so nothing else may compute it a second way.
    """
    return status == DONE


def status_for_done(done: bool) -> str:
    """Which status a bare `done` boolean means.

    The checkbox on the calendar and in the list predates the board and still
    sends a plain tick. Ticking means DONE. **Unticking means TODO, never
    "back to whatever it was"** — nothing records what it was, and guessing
    `in_progress` would silently move a card the user never touched.
    """
    return DONE if done else TODO


def quadrant(urgent: bool | None, important: bool | None) -> str:
    """Which Eisenhower box a task sits in.

    ⚠️ Both answers are needed. A task that is known-urgent but has never been
    asked about importance is still UNSORTED — placing it on one axis only
    would put it in a box on the strength of a coin flip.
    """
    if urgent is None or important is None:
        return UNSORTED
    return _QUADRANTS[(bool(urgent), bool(important))]


def priority_rank(urgent: bool | None, important: bool | None) -> int:
    """Sort key for "by priority". Lower is more pressing."""
    return _PRIORITY_RANK[quadrant(urgent, important)]


def status_rank(status: str) -> int:
    """Sort key for "by status", left-to-right along the board."""
    return _STATUS_RANK.get(status, len(STATUSES))
