"""The personal assistant: his own state, handed to a model that must not guess.

Two halves. `build_context` reads the app and writes down what is true right
now — events, tasks, habits, focus time, books, inbox — and `answer` puts that
in front of DeepSeek with the question. The formatting and the arithmetic live
in the pure `assistant_format.py`, the same split the weekly digest uses.

It is **optional by construction**, exactly like the digest's paragraph: no
`DEEPSEEK_API_KEY`, a timeout, a 500 or an empty completion all come back as
`None`, and the caller says so. Nothing in this app may depend on the model
answering (see `services/llm.py`, and mind its max_tokens warning — DeepSeek's
reasoning models spend the budget before the visible text starts).

The tone is a decision, not a default: he asked for a coach, so the prompt
tells the model to name the habit that is being skipped and the task that is
twelve days late. That only stays honest because the context carries the
counts — the model is never asked to feel anything, only to read.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.services import assistant_format as fmt
from app.services import habits as habits_svc
from app.services import inbox as inbox_svc
from app.services import llm
from app.services import pomodoro as pomodoro_svc
from app.services import reading as reading_svc
from app.services import review as review_svc
from app.services import tasks as tasks_svc
from app.services.calendar import ASTANA

#: How many turns of a website conversation ride along. Telegram sends none.
HISTORY_LIMIT = 10

#: Generous on purpose. DeepSeek's reasoning trace is billed against this, and
#: a tight budget returns HTTP 200 with an EMPTY answer (see llm.py).
MAX_TOKENS = 3000

SYSTEM = (
    "You are Bektas's personal assistant inside his own productivity app. "
    "Answer from the CONTEXT below; if the context doesn't contain the answer, "
    "say so briefly — never invent events, tasks or numbers. "
    "Be concise and direct. Reply in the language the question was asked in.\n"
    "\n"
    "Be honest and direct, like a good coach. When the data shows neglect — "
    "habits going undone, tasks sitting overdue, a week with no focus time — "
    "say it plainly and name the specific habit/task; do not soften it into "
    "generic advice. When the data shows real progress — streaks held, tasks "
    "closed, focus hours up — acknowledge it specifically and tell him to keep "
    "going. Never flatter, never scold beyond what the data supports, always "
    "ground every claim in the context numbers."
)


def build_context(db: Session, now: datetime | None = None) -> str:
    """Everything true about his day right now, in plain labelled text."""
    moment = now or datetime.now(ASTANA)
    today = moment.strftime("%Y-%m-%d")
    tomorrow = (moment.date() + timedelta(days=1)).isoformat()

    blocks = [
        f"NOW\n- {moment.strftime('%Y-%m-%d %H:%M')}, {moment.strftime('%A')} (Asia/Almaty)",
        _events(db, "TODAY'S EVENTS", today),
        _events(db, "TOMORROW'S EVENTS", tomorrow),
        _tasks(db, today),
        _habits(db, today),
        _focus(db, today),
        _reading(db),
        _inbox(db),
    ]
    return "\n\n".join(blocks)


def _events(db: Session, title: str, day: str) -> str:
    events = review_svc.events_of_day(db, day)
    lines = [fmt.event_line(e.starts_at, e.title, e.all_day) for e in events]
    return fmt.section(f"{title} ({day})", lines, empty="nothing scheduled")


def _tasks(db: Session, today: str) -> str:
    """Open tasks, the latest ones first, with the pile's size and age spelled out."""
    open_tasks = tasks_svc.list_tasks(db, include_done=False)
    ordered = fmt.order_tasks(open_tasks, today)
    lines = [fmt.task_line(t.title, t.due_at, today) for t in ordered]
    block = fmt.section(
        f"OPEN TASKS ({len(open_tasks)} open, overdue first, showing {len(ordered)})",
        lines,
        empty="nothing open",
    )
    return f"{block}\n- Overdue: {fmt.overdue_summary(open_tasks, today)}"


def _habits(db: Session, today: str) -> str:
    week = fmt.recent_days(today)
    lines = [
        fmt.habit_line(
            h.name,
            h.category,
            bool(h.completed_days.get(today)),
            fmt.week_done(h.completed_days, week),
        )
        for h in habits_svc.list_habits(db)
    ]
    return fmt.section(f"HABITS ({today}, with last 7 days)", lines, empty="no habits tracked")


def _focus(db: Session, today: str) -> str:
    """Pomodoro minutes, this week against the one before.

    Reuses the existing stats service rather than re-querying sessions — its
    `daily_minutes` map already covers the past year, so both windows are a
    sum over keys. Those keys are UTC days, which is what every pomodoro
    number on the site is counted by; one convention, two surfaces.
    """
    daily = pomodoro_svc.get_stats(db).daily_minutes
    fortnight = fmt.recent_days(today, fmt.WEEK_DAYS * 2)
    this_week = fmt.sum_days(daily, fortnight[fmt.WEEK_DAYS :])
    last_week = fmt.sum_days(daily, fortnight[: fmt.WEEK_DAYS])
    return fmt.section("FOCUS TIME (pomodoro)", [fmt.focus_line(this_week, last_week)])


def _reading(db: Session) -> str:
    books = [i for i in reading_svc.list_reading_items(db) if i.status == "in_progress"]
    lines = [f"{b.title}{f' — {b.author}' if b.author else ''}" for b in books]
    return fmt.section("CURRENTLY READING", lines, empty="no book in progress")


def _inbox(db: Session) -> str:
    count = inbox_svc.count_untriaged(db)
    return fmt.section("INBOX", [f"{count} captured item(s) still waiting to be filed"])


def build_prompt(question: str, history: list[dict] | None = None) -> str:
    """The question, with the last few turns above it for pronouns to point at."""
    turns = [
        f"{'User' if t.get('role') == 'user' else 'Assistant'}: {content}"
        for t in (history or [])[-HISTORY_LIMIT:]
        if (content := (t.get("content") or "").strip())
    ]
    if not turns:
        return f"Question: {question}"
    return "Earlier in this conversation:\n" + "\n".join(turns) + f"\n\nQuestion: {question}"


def answer(db: Session, question: str, history: list[dict] | None = None) -> str | None:
    """His answer, or None — and None is a configuration fact, not an error."""
    text = (question or "").strip()
    if not text:
        return None
    # Checked before the snapshot is built: with no key there is nothing to
    # send, and reading the whole app to throw it away would be a waste.
    if not llm.configured():
        return None

    system = f"{SYSTEM}\n\nCONTEXT\n{build_context(db)}"
    reply = llm.chat(system, build_prompt(text, history), max_tokens=MAX_TOKENS)
    return reply.strip() if reply and reply.strip() else None
