"""Natural reminder parsing, RU + KK.

Written test-first. The parser is a pattern set, not NLP: these cases ARE the
specification of what it promises to understand.

`now` is always passed in so every case is deterministic — no test depends on
the clock. All times are Asia/Almaty.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.reminder_parser import parse_reminder

ASTANA = ZoneInfo("Asia/Almaty")

# A Wednesday, 10:00 Almaty.
NOW = datetime(2026, 8, 12, 10, 0, tzinfo=ASTANA)


def parsed(text: str, now: datetime = NOW):
    return parse_reminder(text, now)


# --- intent ---------------------------------------------------------------


def test_a_message_without_remind_intent_is_not_a_reminder():
    assert parsed("купить молоко") is None
    assert parsed("сәлем, қалайсың?") is None
    assert parsed("") is None


@pytest.mark.parametrize(
    "text",
    [
        "напомни завтра в 15:00 позвонить маме",
        "напомнить завтра в 15:00 позвонить маме",
        "Напомни мне завтра в 15:00 позвонить маме",
        "ертең сағат 15:00 анама қоңырау шалуды еске сал",
        "ертең сағат 15:00 анама қоңырау шалуды ескерт",
    ],
)
def test_remind_intent_is_recognised_in_both_languages(text):
    assert parsed(text) is not None


# --- dates ----------------------------------------------------------------


def test_tomorrow_ru_and_kk():
    for text in ["напомни завтра в 15:00 позвонить", "ертең сағат 15:00 қоңырау шал ескерт"]:
        result = parsed(text)
        assert result.starts_at == "2026-08-13T15:00:00+05:00", text


def test_today_ru_and_kk():
    for text in ["напомни сегодня в 15:00 позвонить", "бүгін сағат 15:00 ескерт"]:
        assert parsed(text).starts_at == "2026-08-12T15:00:00+05:00", text


def test_day_after_tomorrow():
    assert parsed("напомни послезавтра в 9:00 сдать отчёт").starts_at == (
        "2026-08-14T09:00:00+05:00"
    )
    assert parsed("бүрсігүні сағат 9:00 ескерт").starts_at == "2026-08-14T09:00:00+05:00"


def test_a_weekday_means_the_next_one():
    # Wednesday the 12th → "on Friday" is the 14th.
    assert parsed("напомни в пятницу в 12:00 забрать посылку").starts_at == (
        "2026-08-14T12:00:00+05:00"
    )
    assert parsed("жұма күні сағат 12:00 ескерт").starts_at == "2026-08-14T12:00:00+05:00"


def test_the_same_weekday_today_stays_today_when_the_time_is_still_ahead():
    # It is Wednesday 10:00; "Wednesday at 15:00" is five hours away, not a week.
    assert parsed("напомни в среду в 15:00 позвонить").starts_at == (
        "2026-08-12T15:00:00+05:00"
    )


def test_the_same_weekday_rolls_to_next_week_once_the_time_has_passed():
    assert parsed("напомни в среду в 09:00 позвонить").starts_at == (
        "2026-08-19T09:00:00+05:00"
    )


def test_an_explicit_day_and_month():
    assert parsed("напомни 20.08 в 14:30 встреча").starts_at == "2026-08-20T14:30:00+05:00"
    assert parsed("напомни 20.08.2027 в 14:30 встреча").starts_at == (
        "2027-08-20T14:30:00+05:00"
    )


def test_a_past_day_and_month_rolls_to_next_year():
    """01.01 asked in August means the coming January, not a date behind us."""
    assert parsed("напомни 01.01 в 10:00 поздравить").starts_at == (
        "2027-01-01T10:00:00+05:00"
    )


# --- times ----------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("напомни завтра в 15:00 X", "15:00"),
        ("напомни завтра в 15.30 X", "15:30"),
        ("напомни завтра в 15 X", "15:00"),
        ("напомни завтра 15:00 X", "15:00"),
        ("ертең сағат 15:00 X ескерт", "15:00"),
        ("ертең сағат 15те X ескерт", "15:00"),
        ("напомни завтра в 9:05 X", "09:05"),
    ],
)
def test_time_shapes(text, expected):
    assert parsed(text).starts_at[11:16] == expected


def test_evening_words_push_a_bare_hour_into_the_afternoon():
    assert parsed("напомни завтра в 7 вечера позвонить").starts_at[11:16] == "19:00"
    assert parsed("ертең кешке сағат 7 ескерт").starts_at[11:16] == "19:00"
    # Morning stays morning.
    assert parsed("напомни завтра в 7 утра позвонить").starts_at[11:16] == "07:00"


def test_a_reminder_with_no_time_defaults_to_nine_in_the_morning():
    assert parsed("напомни завтра позвонить маме").starts_at == "2026-08-13T09:00:00+05:00"


def test_with_no_date_a_time_still_ahead_means_today():
    assert parsed("напомни в 15:00 позвонить").starts_at == "2026-08-12T15:00:00+05:00"


def test_with_no_date_a_time_already_past_means_tomorrow():
    """The sensible default: you cannot be reminded at 09:00 when it is 10:00."""
    assert parsed("напомни в 09:00 позвонить").starts_at == "2026-08-13T09:00:00+05:00"


def test_a_bare_remind_with_neither_date_nor_time_is_tomorrow_morning():
    assert parsed("напомни позвонить маме").starts_at == "2026-08-13T09:00:00+05:00"


# --- title ----------------------------------------------------------------


def test_the_title_drops_the_intent_and_the_time_words():
    assert parsed("напомни завтра в 15:00 позвонить маме").title == "позвонить маме"
    assert parsed("Напомни мне завтра в 15:00 купить молоко").title == "купить молоко"


def test_the_kazakh_title_drops_its_trailing_intent_word():
    assert parsed("ертең сағат 15:00 анама қоңырау шалуды еске сал").title == (
        "анама қоңырау шалуды"
    )


def test_a_reminder_with_nothing_left_still_gets_a_title():
    result = parsed("напомни завтра в 15:00")
    assert result.title == "Еске салу"


def test_the_reminder_fires_at_the_event_time():
    """"Remind me at 15:00" must ping at 15:00, not fifteen minutes before."""
    assert parsed("напомни завтра в 15:00 X").reminder_minutes == 0
