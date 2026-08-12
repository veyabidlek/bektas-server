"""The model's half of Goals: draft a roadmap, or break a node into tasks.

Two rules, both inherited from `llm.py` and `assistant.py`:

1. **It never raises.** No key, a timeout, a refusal, unparseable JSON — all
   of it comes back as `None`, and the router turns that into a 503 that says
   why. A planning tool must work by hand when the model is unavailable.
2. **The model drafts, it never writes.** These functions return a proposal;
   the caller shows it and only saves what he confirms. An assistant that can
   quietly restructure a roadmap is one bad completion away from destroying it.

`parse_draft` / `parse_tasks` are pure, so the failure modes that actually
happen — a fenced code block, a top-level list, a node with no title, a tree
20 levels deep — are tested without a network.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.services import llm

#: How much of a tree we accept. A model asked for a roadmap will sometimes
#: return a hundred nodes; that is not a plan, it is a wall.
MAX_ROOTS = 10
MAX_CHILDREN = 8
MAX_DEPTH = 3
MAX_TASKS = 12
MAX_TITLE = 120
MAX_DESCRIPTION = 400

_DRAFT_SYSTEM = """You design learning and project roadmaps.

Answer with JSON only, no prose and no code fence:
{"nodes": [{"title": "...", "description": "...", "children": [...]}]}

Rules:
- 4 to 7 top-level areas, ordered so earlier ones unlock later ones.
- 2 to 4 children each, one level deep. Children are concrete topics.
- "description" is ONE short sentence saying what mastering it means.
- Titles are short noun phrases, no numbering, no "Step 1".
"""

_TASKS_SYSTEM = """You turn one roadmap topic into concrete next actions.

Answer with JSON only, no prose and no code fence:
{"tasks": [{"title": "...", "description": "..."}]}

Rules:
- 3 to 6 tasks, each a single doable session of work, in order.
- "title" starts with a verb and names something finishable.
- "description" is one or two sentences on what doing it well looks like.
"""


def _strip_fence(text: str) -> str:
    """Models fence JSON even when told not to. Take what is inside."""
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    return (fenced.group(1) if fenced else text).strip()


def _clean(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _node(raw: Any, depth: int) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    title = _clean(raw.get("title"), MAX_TITLE)
    if not title:
        return None  # a box with no name is not a node
    children: list[dict[str, Any]] = []
    if depth < MAX_DEPTH:
        for child in (raw.get("children") or [])[:MAX_CHILDREN]:
            built = _node(child, depth + 1)
            if built:
                children.append(built)
    return {
        "title": title,
        "description": _clean(raw.get("description"), MAX_DESCRIPTION),
        "children": children,
    }


def parse_draft(text: str) -> list[dict[str, Any]] | None:
    """Model output → a validated tree, or None if there is nothing usable.

    Accepts both the documented `{"nodes": [...]}` and a bare top-level list,
    because that is the shape models actually return about a third of the time.
    """
    try:
        data = json.loads(_strip_fence(text))
    except (ValueError, TypeError):
        return None
    raw_nodes = data.get("nodes") if isinstance(data, dict) else data
    if not isinstance(raw_nodes, list):
        return None
    nodes = [n for n in (_node(r, 1) for r in raw_nodes[:MAX_ROOTS]) if n]
    return nodes or None


def parse_tasks(text: str) -> list[dict[str, str]] | None:
    try:
        data = json.loads(_strip_fence(text))
    except (ValueError, TypeError):
        return None
    raw = data.get("tasks") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return None
    tasks: list[dict[str, str]] = []
    for item in raw[:MAX_TASKS]:
        if isinstance(item, str):
            item = {"title": item}
        if not isinstance(item, dict):
            continue
        title = _clean(item.get("title"), MAX_TITLE)
        if title:
            tasks.append(
                {"title": title, "description": _clean(item.get("description"), MAX_DESCRIPTION)}
            )
    return tasks or None


def draft_roadmap(goal: str) -> list[dict[str, Any]] | None:
    """A proposed tree for `goal`, or None when there is no usable answer."""
    reply = llm.chat(_DRAFT_SYSTEM, goal.strip(), max_tokens=3000, temperature=0.4)
    return parse_draft(reply) if reply else None


def suggest_tasks(node_title: str, goal_title: str, node_description: str = "") -> list[dict[str, str]] | None:
    """Concrete next actions for one node, or None."""
    context = f"Roadmap: {goal_title}\nTopic: {node_title}"
    if node_description.strip():
        context += f"\nNotes: {node_description.strip()}"
    reply = llm.chat(_TASKS_SYSTEM, context, max_tokens=2000, temperature=0.4)
    return parse_tasks(reply) if reply else None
