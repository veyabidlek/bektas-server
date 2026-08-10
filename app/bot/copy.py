"""Bot copy and message formatting.

English, and deliberately the *same vocabulary as the site*: Task, Event, Note,
Diary, Inbox. A thing should not be called one word in the browser and another
in chat.

Formatting lives here too, so a confirmation in chat reads like the card it
corresponds to on the site: a bold title line, then the quiet detail under it.
Telegram HTML, emoji used sparingly as section accents (📅 ✅ 📥 📔 ⏰).
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta

# --- onboarding -----------------------------------------------------------

START = (
    "👋 <b>Bektas Assistant</b>\n"
    "Your personal capture, calendar and review — all in one chat.\n"
    "\n"
    "📥 <b>Capture</b>\n"
    "Send text, a photo or a forward and it lands in your Inbox, with buttons "
    "to file it as Task, Event, Note or Diary.\n"
    "\n"
    "⏰ <b>Reminders</b>\n"
    "Write it the way you'd say it:\n"
    "<code>remind me tomorrow at 15:00 call mum</code>\n"
    "<code>ертең сағат 15:00 анама қоңырау шал ескерт</code>\n"
    "→ straight onto your Calendar.\n"
    "\n"
    "📅 <b>Every morning</b> · 08:00\n"
    "Today's events, tasks and inbox at a glance.\n"
    "\n"
    "🌙 <b>Every evening</b>\n"
    "The review — each of today's events, one tap each, then your score.\n"
    "<code>/review</code> runs it now.\n"
    "\n"
    "🗓 <b>Every Sunday</b>\n"
    "Your week — what happened, what it added up to, what's coming.\n"
    "<code>/digest</code> runs it now.\n"
    "\n"
    "🤖 <b>Ask anything</b>\n"
    "<code>/a what's left today?</code>\n"
    "Answers from your own calendar, tasks, habits and focus time — honestly."
)

# --- the command menu + profile text (set once at startup) ----------------
# The blue "Menu"/"/" list. Sentence case, no trailing period, each line
# saying what the command really does. /help is a working alias of /start and
# is deliberately NOT a second menu row — a duplicate entry reads as noise.
BOT_COMMANDS = [
    {"command": "start", "description": "What this bot does and how to use it"},
    {"command": "a", "description": "Ask your assistant about today, tasks or habits"},
    {"command": "review", "description": "Review today's events and score the day"},
    {"command": "digest", "description": "This week — what happened and what's next"},
]

# The tagline under the bot's name (setMyShortDescription, ≤120 chars).
BOT_SHORT_DESCRIPTION = "Your personal capture, calendar & review assistant."

# The about text on the profile / empty-chat screen (setMyDescription, ≤512).
# Plain text — no HTML here, so the site's words carry the tone on their own.
BOT_DESCRIPTION = (
    "Send me any thought, photo or forward — it lands in your Inbox to file "
    "as a Task, Event, Note or Diary entry.\n\n"
    "Type a reminder like “remind me tomorrow at 15:00 call mum” and it goes "
    "straight onto your Calendar.\n\n"
    "Every morning: today at a glance. Every evening: the review. "
    "Every Sunday: your week.\n\n"
    "Ask me anything about your own day with /a — I answer from your calendar, "
    "tasks and habits, and I tell you the truth about them."
)

REFUSED = "Sorry — this is a private bot."

UNKNOWN_COMMAND = "I don't know that command. Just send me the thought."

# --- the assistant (/a, /ask) ---------------------------------------------
# Plain text going out, not a flow: free text in this chat is Inbox capture, so
# a question has to be asked with the command. Each /a stands on its own —
# there is deliberately no conversation memory here, the same reasoning that
# keeps the diary and review flows stateless.

ASSISTANT_USAGE = (
    "🤖 <b>Ask me about your own day</b>\n"
    "<code>/a what's left today?</code>\n"
    "<code>/a am I keeping up with my habits?</code>\n"
    "\n"
    "Plain text still goes to your Inbox — questions need the command.\n"
    "Each question stands alone; I don't remember the last one."
)

ASSISTANT_UNAVAILABLE = (
    "🤖 The assistant is off — no model is configured.\n"
    "Everything else in this bot works as usual."
)


def assistant_reply(text: str) -> str:
    """The model's answer, plain.

    Every character is escaped: messages go out with parse_mode=HTML and one
    stray "<" from a completion would break the whole send — the same rule
    `weekly_summary.tidy` follows for the digest's paragraph.
    """
    return html.escape(text.strip(), quote=False)

# --- the persistent reply keyboard (sits above the text box) ---------------
# Four taps for the four things worth doing on demand. A tap arrives as a plain
# text message whose text is exactly the label — handlers match these BEFORE the
# capture fallback, so a tap never lands in the Inbox as a note.
BTN_MENU_REVIEW = "🌙 Review"   # → the evening review, now (same as /review)
BTN_MENU_WEEK = "🗓 Week"       # → the weekly digest, now (same as /digest)
BTN_MENU_TODAY = "📅 Today"     # → today's agenda (the morning-digest view)
BTN_MENU_INBOX = "📥 Inbox"     # → what is still waiting in the Inbox
BTN_MENU_DIARY = "📔 Diary"     # → read today's entry, and write into it

MENU_KEYBOARD = [
    [BTN_MENU_REVIEW, BTN_MENU_WEEK],
    [BTN_MENU_TODAY, BTN_MENU_INBOX],
    [BTN_MENU_DIARY],
]

# The set the message handler checks against — a tap is one of exactly these.
MENU_LABELS = {
    BTN_MENU_REVIEW, BTN_MENU_WEEK, BTN_MENU_TODAY, BTN_MENU_INBOX, BTN_MENU_DIARY,
}


def inbox_list(items) -> str:
    """The 📥 button's answer: what is still untriaged, newest first.

    Free-form captured text is escaped — a stray "<" would break an HTML send.
    """
    if not items:
        return "📥 <b>Inbox</b>\nAll clear — nothing to triage."

    lines = [f"📥 <b>Inbox</b> · {len(items)} to triage"]
    for item in items[:15]:
        text = (getattr(item, "text", "") or "").strip().replace("\n", " ")
        if not text:
            text = "🖼 photo" if getattr(item, "images", None) else "(empty)"
        if len(text) > 60:
            text = text[:59] + "…"
        lines.append(f"• {html.escape(text, quote=False)}")
    if len(items) > 15:
        lines.append(f"+{len(items) - 15} more")
    lines.append("\nTap a captured thought on the site to file it.")
    return "\n".join(lines)

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
# The toast on "✅ Right" — confirming a parsed reminder changes nothing, it
# only says so.
DONE_EVENT = "On your calendar."

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


# --- the diary (write from chat, read it back article-style) ---------------

# Settled cards a diary reply ends in.
DIARY_SAVED = "📔 Added to today's diary"
DIARY_PHOTO_SAVED = "📔 Photo added to today's diary"
DIARY_SAVED_BOTH = "📔 Added to today's diary — words and a photo"
DIARY_EMPTY_REPLY = "Reply with a few words or a photo to add to today's diary."

# Markdown → the HTML subset Telegram actually renders: <b> <i> <s> <u> <code>
# <a> <blockquote>. Everything Telegram can't do degrades — headings and bold
# both become <b>, lists become "• ", a rule becomes a thin divider, and images
# are dropped from the text because the photos are sent as real images after it.
_MD_IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_RULE = re.compile(r"^\s*([-*_])\1{2,}\s*$")
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_MD_LIST = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_MD_OLIST = re.compile(r"^(\s*)(\d+)\.\s+(.*)$")
_MD_QUOTE = re.compile(r"^>\s?(.*)$")
_MD_CODE = re.compile(r"`([^`]+)`")
_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_MD_BOLD = re.compile(r"(\*\*|__)(.+?)\1")
_MD_STRIKE = re.compile(r"~~(.+?)~~")
_MD_ITALIC = re.compile(r"(?<![\*_\w])([*_])(?!\s)(.+?)(?<!\s)\1(?![\*_\w])")


def _md_inline(text: str) -> str:
    """Inline spans on an already-HTML-escaped line. Code first so its contents
    are not re-processed as emphasis."""
    text = _MD_CODE.sub(lambda m: f"<code>{m.group(1)}</code>", text)
    text = _MD_LINK.sub(
        lambda m: f'<a href="{m.group(2).replace(chr(34), "%22")}">{m.group(1)}</a>', text
    )
    text = _MD_BOLD.sub(lambda m: f"<b>{m.group(2)}</b>", text)
    text = _MD_STRIKE.sub(lambda m: f"<s>{m.group(1)}</s>", text)
    text = _MD_ITALIC.sub(lambda m: f"<i>{m.group(2)}</i>", text)
    return text


def render_markdown(md: str) -> str:
    """The site's markdown, rendered to Telegram-safe HTML. Read the mapping in
    the module comment above `_MD_IMG`."""
    out: list[str] = []
    for raw in (md or "").split("\n"):
        line = _MD_IMG.sub("", raw)
        if _MD_RULE.match(line):
            out.append("┄┄┄┄┄┄┄┄")
            continue

        heading = _MD_HEADING.match(line.strip())
        bullet = None if heading else _MD_LIST.match(line)
        ordered = None if (heading or bullet) else _MD_OLIST.match(line)
        quote = None if (heading or bullet or ordered) else _MD_QUOTE.match(line)

        if heading:
            content = heading.group(2)
        elif bullet:
            content = bullet.group(2)
        elif ordered:
            content = ordered.group(3)
        elif quote:
            content = quote.group(1)
        else:
            content = line

        rendered = _md_inline(html.escape(content, quote=False))

        if heading:
            rendered = f"<b>{rendered}</b>"
        elif bullet:
            rendered = f"• {rendered}"
        elif ordered:
            rendered = f"{ordered.group(2)}. {rendered}"
        elif quote:
            rendered = f"<blockquote>{rendered}</blockquote>"
        out.append(rendered)

    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _hhmm(iso: str | None) -> str | None:
    return iso[11:16] if iso and len(iso) >= 16 else None


def diary_article(entry) -> str:
    """Today's entry, read like the article it is on the site: a bold title, a
    date line, the body rendered, then a quiet "written HH:MM · N photos" cue."""
    label, _ = _date_parts(entry.day)
    body = render_markdown(entry.body_md)

    if not getattr(entry, "exists", False) or not (body or entry.images):
        return f"📔 <b>Diary</b> · {label}\nToday's diary is empty — start writing."

    title = (entry.title or "").strip()
    head = f"📔 <b>{html.escape(title, quote=False)}</b>" if title else "📔 <b>Diary</b>"
    lines = [head, label]
    if body:
        lines += ["", body]

    cue = []
    written = _hhmm(entry.updated_at)
    if written:
        cue.append(f"written {written}")
    if entry.images:
        n = len(entry.images)
        cue.append(f"{n} photo" + ("s" if n != 1 else ""))
    if cue:
        lines += ["", f"<i>{' · '.join(cue)}</i>"]
    return "\n".join(lines)


def diary_prompt(day: str) -> str:
    """The reply target. Carries the day in its own text so the flow stays
    stateless — a reply quoting this tells the handler which day to write."""
    return (
        "✍️ <b>Write today's diary</b>\n"
        "Reply to this message — text is appended, a photo is attached.\n"
        f"<code>#diary-{day}</code>"
    )


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
