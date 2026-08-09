"""The digest's one paragraph of prose.

The numbers above it are already true and already legible; what a summary adds
is the thread between them — that the week had a shape, and what it was. So the
model is given only *real* material (diary lines, finished tasks, event titles)
and told to say what it sees, in two to four plain sentences.

Everything here degrades to `None`: an unconfigured key, a model failure, or a
week with nothing written in it. The digest simply has no summary section, and
still goes out on time.
"""

from __future__ import annotations

import html
import re

from app.services import llm
from app.services.week_stats import WeekStats
from app.services.weekly import WeekContent

#: Long enough for four sentences, short enough that a runaway completion
#: cannot turn the digest into an essay.
MAX_CHARS = 700

SYSTEM = (
    "You write a short weekly summary for one person, from their own diary "
    "entries, finished tasks and calendar events.\n"
    "Rules:\n"
    "- 2 to 4 sentences, plain English, warm but not flattering.\n"
    "- Address them as 'you'.\n"
    "- Say only what the material shows. Never invent a fact, a feeling or a "
    "number that is not there.\n"
    "- No emoji, no markdown, no headings, no lists, no greeting, no sign-off.\n"
    "- Do not repeat the counts back to them; they can already see those.\n"
    "- If the material is thin, say so briefly rather than padding."
)


def build_user_prompt(stats: WeekStats, content: WeekContent) -> str:
    """The week, as plainly as it can be handed over."""
    lines = [f"Week of {stats.week.start} to {stats.week.end} (Monday to Sunday)."]

    if content.diary:
        lines += ["", "Diary entries:"] + [f"- {line}" for line in content.diary]
    if content.tasks:
        lines += ["", "Tasks completed:"] + [f"- {title}" for title in content.tasks]
    if content.events:
        lines += ["", "Calendar events:"] + [f"- {title}" for title in content.events]

    counts = [
        f"{stats.events} events",
        f"{stats.tasks_done} tasks done",
        f"{stats.diary_days} of 7 days journalled",
    ]
    if stats.effectiveness is not None:
        counts.append(f"{stats.effectiveness}% average effectiveness")
    lines += ["", "For context only, do not restate: " + ", ".join(counts) + "."]

    return "\n".join(lines)


def tidy(text: str) -> str:
    """One paragraph, HTML-safe, capped.

    The digest is sent with `parse_mode=HTML`, so a stray `<` in a completion
    would break the whole message — every character the model produced is
    escaped before it is allowed near Telegram.
    """
    collapsed = re.sub(r"\s+", " ", text.strip())
    if len(collapsed) > MAX_CHARS:
        cut = collapsed[:MAX_CHARS]
        collapsed = cut[: cut.rfind(" ")] if " " in cut else cut
        collapsed = collapsed.rstrip(",;: ") + "…"
    return html.escape(collapsed)


def summarize(stats: WeekStats, content: WeekContent) -> str | None:
    """The paragraph, or None — and None is a perfectly good week."""
    if content.is_empty:
        return None

    reply = llm.chat(SYSTEM, build_user_prompt(stats, content), max_tokens=2000)
    if not reply:
        return None

    tidied = tidy(reply)
    return tidied or None
