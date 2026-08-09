"""The Sunday weekly digest.

Four things have to be true, and they are tested in that order: the week is the
right seven days, the counts are the right counts, the AI paragraph is optional
in every way it can fail, and the message goes out once per Sunday.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from conftest import FakeTelegram

from app.bot import copy, handlers, scheduler
from app.bot import weekly as bot_weekly
from app.schemas.calendar import CalendarEventCreate
from app.schemas.task import TaskCreate
from app.services import calendar as calendar_svc
from app.services import diary as diary_svc
from app.services import inbox as inbox_svc
from app.services import llm
from app.services import review as review_svc
from app.services import tasks as tasks_svc
from app.services import weekly as weekly_svc
from app.services import weekly_summary
from app.services.review_score import summarize
from app.services.week_stats import Week, average, strip, week_of

ASTANA = ZoneInfo("Asia/Almaty")
OWNER = 673615046

# Mon 3 Aug — Sun 9 Aug 2026. The week the digest below is about.
MONDAY = "2026-08-03"
SUNDAY = "2026-08-09"
WEEK = Week(start=MONDAY, end=SUNDAY)


# --- the week window (pure) ------------------------------------------------


def test_the_week_runs_monday_to_sunday():
    assert week_of(MONDAY) == WEEK
    assert week_of("2026-08-06") == WEEK
    assert week_of(SUNDAY) == WEEK


def test_sunday_belongs_to_the_week_that_is_ending_not_the_one_starting():
    """The whole point of the Sunday digest — it closes a week, not opens one."""
    assert week_of(SUNDAY).start == MONDAY
    assert week_of("2026-08-10").start == "2026-08-10"


def test_the_week_is_seven_days_and_knows_the_monday_after_it():
    assert WEEK.days == [f"2026-08-0{n}" for n in range(3, 10)]
    assert WEEK.after == "2026-08-10"


def test_a_week_can_straddle_a_month_and_a_year():
    assert week_of("2026-08-01").start == "2026-07-27"
    assert week_of("2027-01-01") == Week(start="2026-12-28", end="2027-01-03")


def test_the_window_is_taken_from_the_moment_not_from_a_stored_day():
    from app.services.week_stats import week_containing

    assert week_containing(datetime(2026, 8, 9, 20, 0, tzinfo=ASTANA)) == WEEK


# --- the strip and the average (pure) --------------------------------------


def _scores(*percents):
    """A week of DayScores from percentages; None = a day he never reviewed."""
    return [
        summarize(day, 1, [] if percent is None else ["done" if percent else "no"])
        for day, percent in zip(WEEK.days, percents, strict=False)
    ]


def test_the_strip_is_the_dashboards_bars():
    assert strip(_scores(100, 100, 0, 100, None, None, 0)) == "▮▮▯▮▯▯▯"


def test_a_week_he_never_reviewed_has_no_average_rather_than_zero():
    assert average(_scores(None, None, None)) is None


def test_the_average_ignores_unreviewed_days():
    assert average(_scores(100, 100, None, None)) == 100
    assert average(_scores(100, 0)) == 50


# --- the counts (over a real database) -------------------------------------


def _event(db, title: str, starts_at: str):
    return calendar_svc.create_event(
        db, CalendarEventCreate(title=title, starts_at=starts_at)
    )


def _task(db, title: str, *, created: str = MONDAY, done_on: str | None = None, **kwargs):
    """A task, stamped explicitly.

    `created_at` and `done_at` are written by the service from the real clock,
    and a week's counts are exactly a question about those two columns — so the
    fixtures set them, or this suite would start failing the week after it was
    written.
    """
    task = tasks_svc.create_task(db, TaskCreate(title=title, **kwargs))
    task.created_at = f"{created}T09:00:00+05:00"
    if done_on:
        task.done = True
        task.done_at = f"{done_on}T18:00:00+05:00"
    db.commit()
    return task


def _inbox(db, text: str, *, created: str = MONDAY, triaged: str | None = None):
    item = inbox_svc.create_item(db, text)
    item.created_at = f"{created}T09:00:00+05:00"
    if triaged:
        item.triaged_to = "dismissed"
        item.triaged_at = f"{triaged}T10:00:00+05:00"
    db.commit()
    return item


def test_the_week_counts_only_what_happened_inside_it(db):
    inside = _event(db, "Gym", f"{MONDAY}T19:00:00")
    _event(db, "Дәрігер", f"{SUNDAY}T11:00:00")
    _event(db, "Next week", "2026-08-10T09:00:00")
    _event(db, "Last week", "2026-08-02T09:00:00")

    review_svc.record_outcome(db, inside.id, "done")

    _task(db, "Shipped the digest", done_on="2026-08-06")
    _task(db, "Still open")
    _task(db, "From last week", created="2026-07-30")

    diary_svc.upsert_entry(db, "2026-08-05", "Long day, good one.")
    diary_svc.upsert_entry(db, "2026-08-06", "")  # opened, never written

    _inbox(db, "a thought", triaged="2026-08-04")

    stats = weekly_svc.stats_for(db, WEEK)

    assert stats.events == 2
    assert stats.effectiveness == 100  # one day reviewed, and it went well
    assert stats.strip == "▮▯▯▯▯▯▯"
    assert stats.tasks_done == 1
    assert stats.tasks_added == 2
    assert stats.diary_days == 1
    assert (stats.inbox_captured, stats.inbox_triaged) == (1, 1)
    assert stats.is_empty is False


def test_a_week_with_nothing_in_it_says_so(db):
    stats = weekly_svc.stats_for(db, WEEK)
    assert (stats.events, stats.tasks_done, stats.diary_days) == (0, 0, 0)
    assert stats.effectiveness is None
    assert stats.is_empty is True


def test_the_week_ahead_is_next_weeks_events_and_what_is_due(db):
    _event(db, "This week", f"{SUNDAY}T09:00:00")
    _event(db, "Dentist", "2026-08-11T09:00:00")
    _event(db, "Trip", "2026-08-12")

    _task(db, "Due next week", due_at="2026-08-13")
    _task(db, "Due this week", due_at=SUNDAY)
    _task(db, "Already handled", due_at="2026-08-14", done_on="2026-08-07")

    ahead = weekly_svc.ahead(db, WEEK)

    assert ahead.week.start == "2026-08-10"
    assert [title for _, title in ahead.events] == ["Dentist", "Trip"]
    assert ahead.event_count == 2
    assert ahead.tasks == ["Due next week"]
    assert ahead.task_count == 1


def test_the_week_ahead_shows_only_the_first_few_but_counts_them_all(db):
    for day in range(10, 17):
        _event(db, f"Event {day}", f"2026-08-{day}T09:00:00")

    ahead = weekly_svc.ahead(db, WEEK, limit=3)
    assert len(ahead.events) == 3
    assert ahead.event_count == 7


def test_the_summary_sees_his_own_words_not_just_counts(db):
    diary_svc.upsert_entry(db, "2026-08-05", "# Wednesday\n\nFinally shipped it.")
    diary_svc.upsert_entry(db, "2026-08-06", "Quiet.", title="Rest")
    _task(db, "Ship the digest", done_on="2026-08-06")
    _event(db, "Gym", f"{MONDAY}T19:00:00")

    content = weekly_svc.content_for(db, WEEK)

    assert content.diary == ["2026-08-05: Wednesday", "2026-08-06: Rest"]
    assert content.tasks == ["Ship the digest"]
    assert content.events == ["Gym"]
    assert content.is_empty is False


# --- the summary degrades, always ------------------------------------------


def _stats(db):
    return weekly_svc.stats_for(db, WEEK)


def _content():
    return weekly_svc.WeekContent(diary=["2026-08-05: shipped it"], tasks=[], events=[])


def test_without_an_api_key_there_is_simply_no_summary(db, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert llm.configured() is False
    assert weekly_summary.summarize(_stats(db), _content()) is None


def test_a_model_failure_is_a_missing_paragraph_not_a_missing_digest(db, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    def explode(*_args, **_kwargs):
        raise TimeoutError("upstream is having a day")

    monkeypatch.setattr("urllib.request.urlopen", explode)

    assert llm.chat("s", "u") is None
    assert weekly_summary.summarize(_stats(db), _content()) is None
    # And the digest itself still builds, with every section but that one.
    assert "🗓 <b>Your week</b>" in bot_weekly.build_message(db, _sunday_evening())


def test_an_empty_week_is_not_sent_to_the_model_at_all(db, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    called = []
    monkeypatch.setattr(llm, "chat", lambda *a, **k: called.append(a) or "nope")

    assert weekly_summary.summarize(_stats(db), weekly_svc.WeekContent()) is None
    assert called == []


def test_the_models_prose_is_escaped_before_it_reaches_telegram():
    """Telegram parses HTML; one stray '<' would break the whole message."""
    assert weekly_summary.tidy("you & <b>they</b> met") == "you &amp; &lt;b&gt;they&lt;/b&gt; met"
    assert weekly_summary.tidy("two\n\nlines  spaced") == "two lines spaced"


def test_a_runaway_completion_is_cut_rather_than_sent_whole():
    tidied = weekly_summary.tidy("word " * 400)
    assert len(tidied) <= weekly_summary.MAX_CHARS + 1
    assert tidied.endswith("…")


def test_the_prompt_carries_the_week_and_forbids_inventing(db):
    prompt = weekly_summary.build_user_prompt(_stats(db), _content())
    assert f"Week of {MONDAY} to {SUNDAY}" in prompt
    assert "2026-08-05: shipped it" in prompt
    assert "Never invent" in weekly_summary.SYSTEM


# --- the message -----------------------------------------------------------


def _sunday_evening() -> datetime:
    return datetime(2026, 8, 9, 20, 0, tzinfo=ASTANA)


@pytest.fixture()
def _no_llm(monkeypatch):
    """The digest under test never calls out; the summary has its own tests."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


def test_the_message_reads_as_one_card(db, _no_llm):
    inside = _event(db, "Gym", f"{MONDAY}T19:00:00")
    review_svc.record_outcome(db, inside.id, "done")
    _task(db, "Ship the digest", done_on="2026-08-06")
    diary_svc.upsert_entry(db, "2026-08-05", "Long day.")
    _inbox(db, "a thought")
    _event(db, "Dentist", "2026-08-11T09:00:00")
    _task(db, "Call the bank", due_at="2026-08-13", created="2026-08-04")

    assert bot_weekly.build_message(db, _sunday_evening()) == (
        "🗓 <b>Your week</b>\n"
        "3 – 9 Aug\n"
        "\n"
        "📅 <b>Events</b> · 1 · 100% effective\n"
        "▮▯▯▯▯▯▯\n"
        "\n"
        "✅ <b>Tasks</b> · 1 done · 2 added\n"
        "\n"
        "📔 <b>Diary</b> · 1/7 days\n"
        "\n"
        "📥 <b>Inbox</b> · 1 captured · 0 filed\n"
        "\n"
        "📆 <b>Week ahead</b> · 10 – 16 Aug\n"
        "Tue · 09:00 · Dentist\n"
        "\n"
        "✅ <b>Due</b> · 1\n"
        "• Call the bank"
    )


def test_a_quiet_week_still_gets_its_message(db, _no_llm):
    assert bot_weekly.build_message(db, _sunday_evening()) == (
        "🗓 <b>Your week</b>\n"
        "3 – 9 Aug\n"
        "\n"
        "A quiet week — nothing recorded.\n"
        "\n"
        "📆 <b>Week ahead</b> · 10 – 16 Aug\n"
        "Nothing scheduled yet."
    )


def test_the_summary_sits_between_the_numbers_and_what_is_coming(db, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    diary_svc.upsert_entry(db, "2026-08-05", "Shipped it.")
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "You shipped the thing you meant to.")

    text = bot_weekly.build_message(db, _sunday_evening())
    thread = text.index("🧠 <b>The thread</b>")
    assert text.index("📔 <b>Diary</b>") < thread < text.index("📆 <b>Week ahead</b>")
    assert "You shipped the thing you meant to." in text


def test_an_all_day_event_next_week_reads_without_a_time(db, _no_llm):
    _event(db, "Trip", "2026-08-12")
    assert "Wed · Trip" in bot_weekly.build_message(db, _sunday_evening())


def test_the_date_range_says_the_month_once_unless_it_changes():
    assert copy.date_range("2026-08-03", "2026-08-09") == "3 – 9 Aug"
    assert copy.date_range("2026-07-27", "2026-08-02") == "27 Jul – 2 Aug"


# --- when it goes out ------------------------------------------------------


def _at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, minute, tzinfo=ASTANA)


def test_the_digest_goes_out_on_sunday_evening_only():
    assert scheduler.should_send_weekly(_at(9, 20), None, "20:00") is True
    assert scheduler.should_send_weekly(_at(9, 19, 59), None, "20:00") is False
    assert scheduler.should_send_weekly(_at(9, 23), None, "20:00") is True
    # Saturday and Monday are not Sunday, whatever the clock says.
    assert scheduler.should_send_weekly(_at(8, 22), None, "20:00") is False
    assert scheduler.should_send_weekly(_at(10, 9), None, "20:00") is False


def test_it_is_sent_once_however_often_the_bot_restarts():
    assert scheduler.should_send_weekly(_at(9, 20, 1), SUNDAY, "20:00") is False
    assert scheduler.should_send_weekly(_at(9, 22), "2026-08-02", "20:00") is True


def test_the_time_is_his_to_move_and_nonsense_falls_back():
    assert scheduler.should_send_weekly(_at(9, 18), None, "17:30") is True
    assert scheduler.should_send_weekly(_at(9, 18), None, "21:00") is False
    assert scheduler.should_send_weekly(_at(9, 21), None, "not a time") is True
    assert scheduler.should_send_weekly(_at(9, 19), None, "not a time") is False


def test_the_sent_flag_round_trips(db):
    assert scheduler.last_weekly_day(db) is None
    scheduler.record_weekly_sent(db, _at(9, 20))
    assert scheduler.last_weekly_day(db) == SUNDAY


def test_the_digest_time_setting_round_trips_and_is_normalized(db):
    assert weekly_svc.get_digest_time(db) == "20:00"
    assert weekly_svc.set_digest_time(db, "9:5") == "09:05"
    assert weekly_svc.get_digest_time(db) == "09:05"
    with pytest.raises(ValueError):
        weekly_svc.set_digest_time(db, "99:99")


# --- /digest ---------------------------------------------------------------


def _message(text: str) -> dict:
    return {"message_id": 1, "chat": {"id": OWNER}, "from": {"id": OWNER}, "text": text}


def test_slash_digest_sends_the_week_on_demand(db, _no_llm):
    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("/digest"), OWNER)

    assert len(tg.sent) == 1
    assert tg.sent[0]["text"].startswith("🗓 <b>Your week</b>")


def test_the_help_text_mentions_it(db, _no_llm):
    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("/start"), OWNER)
    assert "/digest" in tg.sent[0]["text"]


# --- the API ---------------------------------------------------------------


def test_the_two_bot_times_are_read_and_saved_together(client, auth):
    assert client.get("/api/calendar/review/settings", headers=auth).json() == {
        "review_time": "21:30",
        "weekly_digest_time": "20:00",
    }

    saved = client.put(
        "/api/calendar/review/settings",
        json={"weekly_digest_time": "19:15"},
        headers=auth,
    )
    assert saved.status_code == 200
    # A partial save leaves the other one alone.
    assert saved.json() == {"review_time": "21:30", "weekly_digest_time": "19:15"}

    bad = client.put(
        "/api/calendar/review/settings", json={"weekly_digest_time": "25:00"}, headers=auth
    )
    assert bad.status_code == 422
