"""Bot copy.

English: this is Bektas's own tool, and his personal tools read in English.
(The customer-facing products — shakyrtu and the client sites — stay Kazakh.)
Kept in one place so wording can change without touching the handlers.
"""

START = (
    "Hi Bektas 👋\n"
    "Send me anything and it lands in your Inbox to triage later.\n"
    'Say "remind me tomorrow at 15:00 …" and I\'ll put it on your calendar.'
)

REFUSED = "Sorry — this is a private bot."

UNKNOWN_COMMAND = "I don't know that command. Just send me the thought."

CAPTURED = "✍️ Saved to Inbox."
CAPTURED_PHOTO = "🖼 Photo saved to Inbox."

TRIAGE_PROMPT = "What should it become?"

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

DONE_TASK = "✅ Task added"
DONE_EVENT = "📅 Added to the calendar"
DONE_ARTICLE = "📝 Draft note created (private)"
DONE_DIARY = "📔 Added to today's diary"
DONE_DISMISS = "🗑 Dismissed"

ALREADY_TRIAGED = "That one has already been triaged."
FAILED = "Something went wrong. Try again."

REMINDER_SET = "⏰ Reminder set for {when}\n<b>{title}</b>"
REMINDER_CANCELLED = "Reminder removed — kept it in your Inbox instead."

REMINDER_FIRE = "⏰ <b>{title}</b>\n{when}"

DIGEST_TITLE = "☀️ Today"
DIGEST_EMPTY = "☀️ Nothing planned for today."
DIGEST_TASKS = "📋 Tasks:"
DIGEST_EVENTS = "📅 Events:"
DIGEST_OVERDUE = "⚠️ Overdue:"
