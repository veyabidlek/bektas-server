"""Pure shaping for goals: flat rows in, nested tree and counts out.

No database, no ORM — it takes plain dicts, so the arithmetic that the page
and the assistant both depend on is testable without a session. Same split as
`week_stats.py` beside `weekly.py`.
"""

from __future__ import annotations

from typing import Any


def nest(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flat nodes → roots with `children`, every level ordered.

    Ordering is `position` then `title`, so two nodes minted in the same
    request (identical position) still come back in a stable order rather than
    whatever the database felt like.

    A node whose parent is missing is treated as a ROOT rather than dropped: a
    half-deleted subtree should still be visible and fixable, not invisible.
    """
    by_id = {n["id"]: {**n, "children": []} for n in nodes}
    roots: list[dict[str, Any]] = []
    for node in by_id.values():
        parent = by_id.get(node["parent_id"]) if node["parent_id"] else None
        if parent is None:
            roots.append(node)
        else:
            parent["children"].append(node)

    def sort(level: list[dict[str, Any]]) -> list[dict[str, Any]]:
        level.sort(key=lambda n: (n.get("position", 0), n.get("title", "")))
        for n in level:
            sort(n["children"])
        return level

    return sort(roots)


def counts(tasks: list[dict[str, Any]]) -> tuple[int, int]:
    """(done, total) over a flat list of tasks."""
    return sum(1 for t in tasks if t.get("done")), len(tasks)


def next_due(tasks: list[dict[str, Any]]) -> str | None:
    """The soonest deadline still worth showing.

    Done tasks are skipped — a finished task's date is history, and surfacing
    it as "next up" would make a completed goal look overdue. Comparison is a
    plain string compare, which is correct for both shapes stored in `due_at`:
    "2026-08-20" and "2026-08-20T14:30:00+05:00" sort together because the day
    is the prefix of the datetime.
    """
    pending = [t["due_at"] for t in tasks if t.get("due_at") and not t.get("done")]
    return min(pending) if pending else None


def next_position(siblings: list[dict[str, Any]]) -> int:
    """Where a newly added sibling goes: after everything, with a gap.

    The gap is what lets a later insert land between two rows without
    renumbering them.
    """
    return (max((s.get("position", 0) for s in siblings), default=-10) // 10 + 1) * 10
