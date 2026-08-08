"""Bot copy and message formatting.

English, and deliberately the *same vocabulary as the site*: Task, Event, Note,
Diary, Inbox. A thing should not be called one word in the browser and another
in chat.

Formatting lives here too, so a confirmation in chat reads like the card it
corresponds to on the site: a bold title line, then the quiet detail under it.
Telegram HTML, emoji used sparingly as section accents (📅 ✅ 📥 📔 ⏰).
"""

from __future__ import annotations

from datetime import datetime, timedelta

# --- onboarding -----------------------------------------------------------

START = (
    "<b>Bektas Assistant</b>\n"
    "Send me anything and it lands in your Inbox.\n"
    "\n"
    "<b>Capture</b>\n"
    "Text, a photo or a forward → Inbox, with buttons to file it as "
    "Task, Event, Note or Diary.\n"
    "\n"
    "<b>Reminders</b>\n"
    "<code>remind me tomorrow at 15:00 call mum</code>\n"
    "<code>ертең сағат 15:00 анама қоңырау шал ескерт</code>\n"
    "→ straight onto your Calendar.\n"
    "\n"
    "<b>Every morning</b>\n"
    "08:00 — today's events, tasks and inbox."
)

REFUSED = "Sorry — this is a private bot."

UNKNOWN_COMMAND = "I don't know that command. Just send me the thought."

# --- capture --------------------------------------------------------------

CAPTURED = "📥 Saved to Inbox"
CAPTURED_PHOTO = "📥 Photo saved to Inbox"
TRIAGE_PROMPT = "File it as:"

# --- buttons (the site's words, exactly) ----------------------------------

BTN_TASK = "Task"
BTN_EVENT = "Event"
BTN_ARTICLE = "Note"
BTN_DIARY = "Diary"
BTN_DISMISS = "✕"

BTN_TODAY = "Today"
BTN_TOMORROW = "Tomorrow"
BTN_WEEK = "Next week"

BTN_CONFIRM = "✅ Right"
BTN_EDIT = "✏️ Change"

WHEN_PROMPT_TASK = "Due when?"
WHEN_PROMPT_EVENT = "When?"

ALREADY_TRIAGED = "Already filed."
FAILED = "Something went wrong. Try again."
REMINDER_CANCELLED = "📥 Reminder removed — kept in your Inbox."

DONE_DISMISS = "Dismissed"

# --- formatting helpers ---------------------------------------------------

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _date_parts(iso: str) -> tuple[str, str | None]:
    """("Sat, 9 Aug", "15:00") — the time is None for an all-day thing."""
    day = datetime.fromisoformat(iso) if len(iso) > 10 else datetime.fromisoformat(iso + "T00:00:00")
    label = f"{WEEKDAYS[day.weekday()]}, {day.day} {MONTHS[day.month - 1]}"
    time = iso[11:16] if len(iso) >= 16 else None
    return label, time


def when_line(iso: str) -> str:
    """"📅 Sat, 9 Aug · 15:00" — the site's date-then-time reading order."""
    label, time = _date_parts(iso)
    return f"📅 {label} · {time}" if time else f"📅 {label}"


def due_chip(due_at: str | None, today: str) -> str:
    """"Due: Today" / "Due: Tomorrow" / "Due: 9 Aug" — the site's due chip."""
    if not due_at:
        return "No due date"

    day = due_at[:10]
    tomorrow = (datetime.fromisoformat(today) + timedelta(days=1)).strftime("%Y-%m-%d")
    if day == today:
        label = "Today"
    elif day == tomorrow:
        label = "Tomorrow"
    else:
        parsed = datetime.fromisoformat(day)
        label = f"{parsed.day} {MONTHS[parsed.month - 1]}"

    time = due_at[11:16] if len(due_at) >= 16 else None
    return f"Due: {label} · {time}" if time else f"Due: {label}"


def reminder_line(minutes: int | None) -> str | None:
    if minutes is None:
        return None
    if minutes == 0:
        return "⏰ Reminder at the time"
    if minutes % 1440 == 0:
        return f"⏰ Reminder {minutes // 1440}d before"
    if minutes % 60 == 0:
        return f"⏰ Reminder {minutes // 60}h before"
    return f"⏰ Reminder {minutes}m before"


def event_confirmation(title: str, starts_at: str, reminder_minutes: int | None) -> str:
    lines = [f"📅 <b>{title}</b>", when_line(starts_at)]
    reminder = reminder_line(reminder_minutes)
    if reminder:
        lines.append(reminder)
    return "\n".join(lines)


def task_confirmation(title: str, due_at: str | None, today: str) -> str:
    return f"✅ <b>{title}</b>\n{due_chip(due_at, today)}"


def note_confirmation(title: str) -> str:
    return f"📝 <b>{title}</b>\nDraft note · private"


def diary_confirmation(day: str) -> str:
    label, _ = _date_parts(day)
    return f"📔 Added to your Diary\n{label}"


def reminder_fire(title: str, starts_at: str) -> str:
    label, time = _date_parts(starts_at)
    return f"⏰ <b>{title}</b>\n{time or label}"


def digest(
    today_iso: str,
    events: list[tuple[str | None, str]],
    tasks: list[str],
    overdue: int,
    inbox: int,
) -> str:
    """The 08:00 message, laid out like the site's morning screen.

    "Today" header → the events timeline → due tasks with counts → inbox, and
    each section is simply absent when it is empty.
    """
    label, _ = _date_parts(today_iso)
    lines = ["<b>Today</b>", label]

    if events:
        lines += ["", "📅 <b>Events</b>"]
        lines += [f"{time or '—'} · {title}" for time, title in events]

    if tasks or overdue:
        count = f"{len(tasks)} due" if tasks else "none due"
        lines += ["", f"✅ <b>Tasks</b> · {count}"]
        lines += [f"• {title}" for title in tasks]
        if overdue:
            lines.append(f"⚠️ {overdue} overdue")

    if inbox:
        lines += ["", f"📥 <b>Inbox</b> · {inbox} to triage"]

    if not events and not tasks and not overdue and not inbox:
        lines += ["", "Nothing scheduled. A good day to write."]

    return "\n".join(lines)
