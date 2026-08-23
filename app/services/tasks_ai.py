"""The model's half of Tasks: turn a sentence into tasks, or read the board.

Both rules are inherited from `goals_ai.py`, which is the reference here:

1. **It never raises.** No key, a timeout, unparseable JSON — all `None`, and
   the router turns that into a 503 that says why, or drops the paragraph.
2. **⚠️ The model DRAFTS, it never writes.** `capture` returns proposals. The
   only thing that creates a task is Bektas pressing Add on one. An assistant
   that can quietly write to the backlog is one bad completion away from
   filling it with invented work — and unlike a roadmap, a task list is
   something he acts on without re-reading.

The parsers are pure, so the failure modes that actually happen — a fenced
block, a bare list, a task with no title, a made-up date, `urgent: "yes"` —
are tested without a network.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.services import llm

MAX_TASKS = 8
MAX_TITLE = 120
MAX_NOTES = 400

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_CAPTURE_SYSTEM = """You turn a person's note to themselves into task records.

Answer with JSON only, no prose and no code fence:
{"tasks": [{"title": "...", "notes": "...", "due_at": "YYYY-MM-DD" or null,
            "urgent": true/false/null, "important": true/false/null}]}

Rules:
- One task per distinct thing to do. Usually that is ONE task. Only split when
  the note plainly describes several separate jobs.
- "title" starts with a verb, names something finishable, no trailing period.
- "notes" is empty unless the note carried detail the title had to drop.
- "due_at" ONLY when the note states or clearly implies a date. Resolve
  relative dates ("tomorrow", "next Friday") against the date you are given.
  If no date is implied, use null. Never invent a deadline.
- "urgent" is about time pressure; "important" is about consequence. Set them
  ONLY when the note makes it obvious. Otherwise null — a wrong guess here
  files the task in the wrong quadrant, and null simply means "not triaged".
"""

_ANALYSIS_SYSTEM = """You are looking at someone's task board and telling them
what you see. You are an honest coach, not a cheerleader.

You are given counts. Use ONLY those numbers — never invent a task, a trend or
a date that is not in them.

Answer in 2 to 4 short sentences of plain prose. No lists, no headings, no
markdown. Lead with the thing that most needs attention; if nothing does, say
so plainly and briefly. If a number is zero, do not congratulate them for it
unless it is genuinely the story.
"""


def _strip_fence(text: str) -> str:
    """Models fence JSON even when told not to. Take what is inside."""
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    return (fenced.group(1) if fenced else text).strip()


def _clean(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _tri(value: Any) -> bool | None:
    """A tri-state boolean, defaulting to "not answered".

    ⚠️ Anything the model returns that is not plainly true or false becomes
    None, NOT False. False is a real answer — it puts a task in "Eliminate" —
    and a parser that reaches it by accident is a parser that quietly triages
    the backlog wrong.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes"):
            return True
        if lowered in ("false", "no"):
            return False
    return None


def _due(value: Any) -> str | None:
    """A plain day, or nothing.

    Only the exact "YYYY-MM-DD" shape is accepted. A model that answers
    "tomorrow" or "2026-8-3" is handing over something no reader of this
    column can compare, and a wrong deadline is worse than no deadline.
    """
    text = str(value or "").strip()
    return text if _DATE.match(text) else None


def parse_capture(text: str) -> list[dict[str, Any]] | None:
    """Model output → validated task proposals, or None if nothing is usable.

    Accepts the documented `{"tasks": [...]}`, a bare top-level list, and a
    list of plain strings — the three shapes models actually return.
    """
    try:
        data = json.loads(_strip_fence(text))
    except (ValueError, TypeError):
        return None
    raw = data.get("tasks") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return None

    tasks: list[dict[str, Any]] = []
    for item in raw[:MAX_TASKS]:
        if isinstance(item, str):
            item = {"title": item}
        if not isinstance(item, dict):
            continue
        title = _clean(item.get("title"), MAX_TITLE)
        if not title:
            continue  # a task with no name is not a task
        tasks.append(
            {
                "title": title,
                "notes": _clean(item.get("notes"), MAX_NOTES),
                "due_at": _due(item.get("due_at")),
                "urgent": _tri(item.get("urgent")),
                "important": _tri(item.get("important")),
            }
        )
    return tasks or None


def capture(note: str, today: str) -> list[dict[str, Any]] | None:
    """Proposed tasks for a free-text note. Nothing is saved by this."""
    prompt = f"Today is {today}.\n\nNote:\n{note.strip()}"
    reply = llm.chat(_CAPTURE_SYSTEM, prompt, max_tokens=1500, temperature=0.2)
    return parse_capture(reply) if reply else None


def analyse(context: str) -> str | None:
    """A paragraph about the board, or None — the caller still shows the numbers."""
    reply = llm.chat(_ANALYSIS_SYSTEM, context, max_tokens=1200, temperature=0.5)
    return reply.strip() if reply else None
