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
    "08:00 — today's events, tasks and inbox.\n"
    "\n"
    "<b>Every evening</b>\n"
    "The review: each of today's events, one tap each, then your score.\n"
    "<code>/review</code> runs it now.\n"
    "\n"
    "<b>Every Sunday</b>\n"
    "The week: what happened, what it added up to, what is coming.\n"
    "<code>/digest</code> runs it now."
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


# --- the evening review ---------------------------------------------------

BTN_DONE = "✅ Done"
BTN_PARTIAL = "🟡 Partly"
BTN_NO = "❌ No"
BTN_NOTE = "📝 Note"
BTN_FINISH = "Finish"

OUTCOME_LINE = {"done": "✅ Done", "partial": "🟡 Partly", "no": "❌ No"}

REVIEW_NOTHING = "Nothing was on the calendar today."
REVIEW_UNANSWERED = "Nothing answered yet — tap one of the buttons above."
NOTE_SAVED = "📝 Noted."
NOTE_ORPHANED = "Answer that one first, then add the note."
RECORDED = "Recorded."


def review_header(today_iso: str) -> str:
    """Opens the review — the same Today header the digest uses."""
    label, _ = _date_parts(today_iso)
    return f"🌙 <b>Evening review</b>\n{label}\nHow did today go?"


def review_card(title: str, starts_at: str, all_day: bool = False) -> str:
    """One event, compact: "07:00 · <b>Wake up</b>"."""
    time = None if all_day else (starts_at[11:16] if len(starts_at) >= 16 else None)
    return f"{time or '—'} · <b>{title}</b>"


def review_settled(
    title: str, starts_at: str, outcome: str, note: str | None = None, all_day: bool = False
) -> str:
    """The card after he has answered — the settled state the message becomes."""
    lines = [review_card(title, starts_at, all_day), OUTCOME_LINE.get(outcome, outcome)]
    if note:
        lines.append(f"📝 {note}")
    return "\n".join(lines)


def note_prompt(title: str, event_id: str, card_message_id: int | None = None) -> str:
    """Asks for the note, and carries the target in the message itself.

    The tag is what makes the note flow stateless: his reply quotes this
    message, so the handler reads the event (and the card to update) straight
    off the quoted text instead of remembering a conversation.
    """
    tag = f"#ev-{event_id}" + (f"-{card_message_id}" if card_message_id else "")
    return f"📝 <b>{title}</b>\nReply to this message with your note.\n<code>{tag}</code>"


def breakdown(done: int, partial: int, reviewed: int) -> str:
    """"4/6 done, 1 partly" — the counts behind the percentage."""
    parts = [f"{done}/{reviewed} done"]
    if partial:
        parts.append(f"{partial} partly")
    return ", ".join(parts)


def score_line(done: int, partial: int, reviewed: int, percent: int) -> str:
    """"4/6 done, 1 partly — 75%", the whole thing on one line."""
    return f"{breakdown(done, partial, reviewed)} — {percent}%"


def day_score(done: int, partial: int, reviewed: int, percent: int) -> str:
    """The closing card of a review: the number, then what it is made of."""
    return f"📊 <b>Effectiveness — {percent}%</b>\n{breakdown(done, partial, reviewed)}"


def digest(
    today_iso: str,
    events: list[tuple[str | None, str]],
    tasks: list[str],
    overdue: int,
    inbox: int,
    yesterday=None,
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

    # How yesterday actually went — one line, and only when he reviewed it.
    if yesterday is not None and yesterday.percent is not None:
        lines += [
            "",
            "📊 <b>Yesterday</b> · "
            + score_line(
                yesterday.done, yesterday.partial, yesterday.reviewed, yesterday.percent
            ),
        ]

    return "\n".join(lines)


# --- the Sunday weekly digest ---------------------------------------------


def date_range(start: str, end: str) -> str:
    """"3 – 9 Aug", or "30 Jul – 5 Aug" when the week straddles two months."""
    first = datetime.fromisoformat(start)
    last = datetime.fromisoformat(end)
    left = f"{first.day} {MONTHS[first.month - 1]}" if first.month != last.month else f"{first.day}"
    return f"{left} – {last.day} {MONTHS[last.month - 1]}"


def _ahead_event(starts_at: str, title: str) -> str:
    """"Mon · 09:00 · Dentist", or "Mon · Dentist" for an all-day one."""
    label, time = _date_parts(starts_at)
    weekday = label.split(",")[0]
    return f"{weekday} · {time} · {title}" if time else f"{weekday} · {title}"


def weekly_digest(stats, ahead, summary: str | None = None) -> str:
    """The Sunday message: the week behind, the thread through it, the week ahead.

    `stats` and `ahead` are the dataclasses from `app/services/weekly.py`; they
    are read, never built here, so the counting stays in one place and the
    wording in another. Empty sections are absent rather than zeroed, the same
    rule the morning digest follows.
    """
    lines = ["🗓 <b>Your week</b>", date_range(stats.week.start, stats.week.end)]

    if stats.events:
        headline = f"📅 <b>Events</b> · {stats.events}"
        if stats.effectiveness is not None:
            headline += f" · {stats.effectiveness}% effective"
        lines += ["", headline]
        # The strip only means something once a day has been reviewed.
        if stats.effectiveness is not None:
            lines.append(stats.strip)

    if stats.tasks_done or stats.tasks_added:
        lines += ["", f"✅ <b>Tasks</b> · {stats.tasks_done} done · {stats.tasks_added} added"]

    if stats.diary_days:
        lines += ["", f"📔 <b>Diary</b> · {stats.diary_days}/7 days"]

    if stats.inbox_captured or stats.inbox_triaged:
        lines += [
            "",
            f"📥 <b>Inbox</b> · {stats.inbox_captured} captured · {stats.inbox_triaged} filed",
        ]

    if stats.is_empty:
        lines += ["", "A quiet week — nothing recorded."]

    if summary:
        lines += ["", "🧠 <b>The thread</b>", summary]

    lines += ["", f"📆 <b>Week ahead</b> · {date_range(ahead.week.start, ahead.week.end)}"]

    if ahead.events:
        lines += [_ahead_event(starts_at, title) for starts_at, title in ahead.events]
        if ahead.event_count > len(ahead.events):
            lines.append(f"+{ahead.event_count - len(ahead.events)} more")

    if ahead.tasks:
        lines += ["", f"✅ <b>Due</b> · {ahead.task_count}"]
        lines += [f"• {title}" for title in ahead.tasks]
        if ahead.task_count > len(ahead.tasks):
            lines.append(f"+{ahead.task_count - len(ahead.tasks)} more")

    if not ahead.events and not ahead.tasks:
        lines.append("Nothing scheduled yet.")

    return "\n".join(lines)
