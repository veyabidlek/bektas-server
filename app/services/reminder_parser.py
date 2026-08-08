"""Turn «напомни завтра в 15:00 позвонить маме» into a calendar event.

A pattern set, not NLP. Bektas writes his reminders in Russian and Kazakh in a
handful of shapes; matching those well beats a dependency that half-understands
everything. Anything it does not recognise returns None and is captured as a
plain inbox item instead — the safe direction.

Pure: `now` is a parameter, so behaviour is testable and never depends on the
clock. All arithmetic happens in Asia/Almaty.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ASTANA = ZoneInfo("Asia/Almaty")

DEFAULT_HOUR = 9
FALLBACK_TITLE = "Еске салу"

# Phrases that mean "remind me". Longest first so «еске сал» wins over «сал».
INTENT_PATTERNS = [
    r"напомнить",
    r"напоминай",
    r"напомни(?:\s+мне)?",
    r"еске\s+салшы",
    r"еске\s+сал(?:ып\s+қой)?",
    r"ескерт(?:ші|іп\s+қой)?",
]

RELATIVE_DAYS = {
    "послезавтра": 2,
    "бүрсігүні": 2,
    "завтра": 1,
    "ертең": 1,
    "сегодня": 0,
    "бүгін": 0,
}

# Monday = 0, to match datetime.weekday().
WEEKDAYS = {
    "понедельник": 0, "дүйсенбі": 0,
    "вторник": 1, "сейсенбі": 1,
    "среду": 2, "среда": 2, "сәрсенбі": 2,
    "четверг": 3, "бейсенбі": 3,
    "пятницу": 4, "пятница": 4, "жұма": 4,
    "субботу": 5, "суббота": 5, "сенбі": 5,
    "воскресенье": 6, "жексенбі": 6,
}

EVENING_WORDS = ("вечера", "вечером", "кешке", "кеште")
MORNING_WORDS = ("утра", "утром", "таңертең", "таңда")

# Words that carry no meaning once the date and time are extracted.
NOISE = (
    "сағат", "күні", "мне", "в", "на", "о", "об", "что", "чтобы",
)


@dataclass
class ParsedReminder:
    """A reminder ready to become a calendar event."""

    title: str
    starts_at: str
    # 0 = ping at the event time, which is what "remind me at 15:00" means.
    reminder_minutes: int = 0


def _has_intent(text: str) -> re.Match | None:
    for pattern in INTENT_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match
    return None


def _extract_time(text: str) -> tuple[int, int, str] | None:
    """(hour, minute, remaining text) or None."""
    # 15:00 / 15.30 — an explicit minute.
    match = re.search(r"\b(?:в|сағат)?\s*(\d{1,2})[:.](\d{2})\b", text, re.IGNORECASE)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour < 24 and minute < 60:
            return hour, minute, text[: match.start()] + " " + text[match.end() :]

    # «в 15», «сағат 15», «сағат 15те» — a bare hour, but only where a marker
    # says it is a time. A loose number would swallow "позвонить 2 раза".
    match = re.search(
        r"(?:\bв\b|\bсағат\b)\s*(\d{1,2})(?:\s*(?:те|та|де|да|ке|қа))?\b",
        text,
        re.IGNORECASE,
    )
    if match:
        hour = int(match.group(1))
        if hour < 24:
            return hour, 0, text[: match.start()] + " " + text[match.end() :]

    return None


def _apply_daypart(hour: int, text: str) -> int:
    """«7 вечера» is 19:00; «7 утра» stays 07:00."""
    lowered = text.lower()
    if hour < 12 and any(word in lowered for word in EVENING_WORDS):
        return hour + 12
    if hour == 12 and any(word in lowered for word in MORNING_WORDS):
        return 0
    return hour


def _extract_date(
    text: str, now: datetime
) -> tuple[datetime | None, str, bool]:
    """(date at midnight, remaining text, was a weekday matched)."""
    lowered = text.lower()

    # dd.mm(.yyyy)
    match = re.search(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\b", text)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        year = int(match.group(3)) if match.group(3) else now.year
        try:
            candidate = now.replace(
                year=year, month=month, day=day, hour=0, minute=0, second=0, microsecond=0
            )
        except ValueError:
            candidate = None
        if candidate:
            # A bare dd.mm already behind us means the coming year.
            if not match.group(3) and candidate.date() < now.date():
                candidate = candidate.replace(year=year + 1)
            remaining = text[: match.start()] + " " + text[match.end() :]
            return candidate, remaining, False

    for word, offset in RELATIVE_DAYS.items():
        if word in lowered:
            base = (now + timedelta(days=offset)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            return base, re.sub(word, " ", text, flags=re.IGNORECASE), False

    for word, weekday in WEEKDAYS.items():
        if word in lowered:
            ahead = (weekday - now.weekday()) % 7
            base = (now + timedelta(days=ahead)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            return base, re.sub(word, " ", text, flags=re.IGNORECASE), True

    return None, text, False


def _clean_title(text: str) -> str:
    without_daypart = re.sub(
        "|".join(EVENING_WORDS + MORNING_WORDS), " ", text, flags=re.IGNORECASE
    )
    words = [
        word
        for word in re.split(r"\s+", without_daypart.strip())
        if word and word.lower().strip(",.!?") not in NOISE
    ]
    title = " ".join(words).strip(" ,.–-—:")
    return title or FALLBACK_TITLE


def parse_reminder(text: str, now: datetime | None = None) -> ParsedReminder | None:
    """A reminder, or None when the message is not one."""
    if not text or not text.strip():
        return None

    now = (now or datetime.now(ASTANA)).astimezone(ASTANA)

    intent = _has_intent(text)
    if not intent:
        return None

    rest = text[: intent.start()] + " " + text[intent.end() :]

    # Date first, deliberately: "20.08" and "20:08" are the same shape, so the
    # time pattern would happily read a date as 20:08 if it went first.
    date_part, rest_after_date, matched_weekday = _extract_date(rest, now)
    time_part = _extract_time(rest_after_date)
    remaining = time_part[2] if time_part else rest_after_date

    if time_part:
        hour, minute = time_part[0], time_part[1]
        hour = _apply_daypart(hour, text)
    else:
        hour, minute = DEFAULT_HOUR, 0

    if date_part is not None:
        when = date_part.replace(hour=hour, minute=minute)
        # "Wednesday at 15:00" said on Wednesday morning means today; said in
        # the evening it means next week.
        if matched_weekday and when <= now:
            when += timedelta(days=7)
    else:
        when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # You cannot be reminded at 09:00 when it is already 10:00.
        if when <= now:
            when += timedelta(days=1)

    when = when.replace(second=0, microsecond=0)

    return ParsedReminder(
        title=_clean_title(remaining),
        starts_at=when.isoformat(),
        reminder_minutes=0,
    )
