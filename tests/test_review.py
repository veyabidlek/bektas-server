"""The evening calendar review.

He plans the day in the calendar — "07:00 wake up" — and the review is how he
finds out whether the plan and the day agreed. The arithmetic is pure and
tested first; the rest exercises the real handlers with Telegram replaced by a
recorder.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from conftest import FakeTelegram

from app.bot import handlers, review, scheduler
from app.schemas.calendar import CalendarEventCreate
from app.services import calendar as calendar_svc
from app.services import review as review_svc
from app.services.review_score import summarize

ASTANA = ZoneInfo("Asia/Almaty")
OWNER = 673615046
DAY = "2026-08-12"


# --- the score math (pure) -------------------------------------------------


def test_the_day_score_is_his_example():
    """4 done, 1 partly, 1 no over six events — "Effectiveness: 75%"."""
    score = summarize(DAY, 6, ["done"] * 4 + ["partial", "no"])
    assert (score.done, score.partial, score.no) == (4, 1, 1)
    assert score.reviewed == 6
    assert score.percent == 75


def test_partly_is_worth_half():
    assert summarize(DAY, 2, ["partial", "partial"]).percent == 50
    assert summarize(DAY, 2, ["done", "no"]).percent == 50


def test_a_perfect_and_a_lost_day():
    assert summarize(DAY, 3, ["done"] * 3).percent == 100
    assert summarize(DAY, 3, ["no"] * 3).percent == 0


def test_unanswered_events_do_not_count_against_him():
    """Four planned, two answered, both done — that is 100% of what he answered."""
    score = summarize(DAY, 4, ["done", "done"])
    assert score.total == 4
    assert score.reviewed == 2
    assert score.percent == 100


def test_a_day_nobody_reviewed_has_no_percentage_rather_than_zero():
    score = summarize(DAY, 5, [])
    assert score.percent is None
    assert score.has_data is False


def test_the_percentage_is_a_whole_number():
    assert summarize(DAY, 3, ["done", "done", "no"]).percent == 67


def test_an_unknown_outcome_is_ignored_rather_than_scored():
    assert summarize(DAY, 2, ["done", "maybe"]).reviewed == 1


# --- recording -------------------------------------------------------------


def _event(db, title: str, starts_at: str):
    return calendar_svc.create_event(
        db, CalendarEventCreate(title=title, starts_at=starts_at)
    )


def test_an_answer_is_recorded_once_and_re_answering_overwrites_it(db):
    event = _event(db, "Wake up", f"{DAY}T07:00:00")

    review_svc.record_outcome(db, event.id, "done")
    review_svc.record_outcome(db, event.id, "no")

    from app.models.event_outcome import EventOutcome

    rows = db.query(EventOutcome).all()
    assert len(rows) == 1
    assert rows[0].outcome == "no"


def test_a_note_survives_a_changed_answer(db):
    event = _event(db, "Gym", f"{DAY}T19:00:00")
    review_svc.record_outcome(db, event.id, "partial", note="left early")
    review_svc.record_outcome(db, event.id, "done")

    assert review_svc.get_outcome(db, event.id).note == "left early"


def test_a_note_needs_an_answer_to_attach_to(db):
    event = _event(db, "Read", f"{DAY}T22:00:00")
    assert review_svc.set_note(db, event.id, "later") is None


def test_the_day_score_reads_only_that_day_s_events(db):
    morning = _event(db, "Wake up", f"{DAY}T07:00:00")
    _event(db, "Gym", f"{DAY}T19:00:00")
    other = _event(db, "Tomorrow", "2026-08-13T09:00:00")

    review_svc.record_outcome(db, morning.id, "done")
    review_svc.record_outcome(db, other.id, "no")

    score = review_svc.day_score(db, DAY)
    assert score.total == 2
    assert score.reviewed == 1
    assert score.percent == 100


def test_deleting_the_event_takes_its_outcome_with_it(db):
    event = _event(db, "Cancelled", f"{DAY}T12:00:00")
    review_svc.record_outcome(db, event.id, "done")

    calendar_svc.delete_event(db, calendar_svc.get_event(db, event.id))
    review_svc.delete_outcome(db, event.id)

    assert review_svc.day_score(db, DAY).total == 0


# --- when it goes out ------------------------------------------------------


def _at(hour: int, minute: int) -> datetime:
    return datetime(2026, 8, 12, hour, minute, tzinfo=ASTANA)


def test_the_review_goes_out_once_a_day_at_the_configured_time():
    assert scheduler.should_send_review(_at(21, 30), None, "21:30") is True
    assert scheduler.should_send_review(_at(21, 29), None, "21:30") is False
    assert scheduler.should_send_review(_at(23, 0), None, "21:30") is True
    # Already asked today — a restart at 21:31 must not ask everything twice.
    assert scheduler.should_send_review(_at(22, 0), DAY, "21:30") is False
    assert scheduler.should_send_review(_at(22, 0), "2026-08-11", "21:30") is True


def test_the_time_is_his_to_move():
    assert scheduler.should_send_review(_at(19, 0), None, "18:45") is True
    assert scheduler.should_send_review(_at(19, 0), None, "23:00") is False


def test_a_broken_time_setting_falls_back_instead_of_silencing_the_review():
    assert scheduler.should_send_review(_at(22, 0), None, "not a time") is True
    assert scheduler.should_send_review(_at(20, 0), None, "not a time") is False


def test_the_review_time_setting_round_trips_and_is_normalized(db):
    assert review_svc.get_review_time(db) == "21:30"
    assert review_svc.set_review_time(db, "9:5") == "09:05"
    assert review_svc.get_review_time(db) == "09:05"


# --- the flow in chat ------------------------------------------------------


def _callback(data: str, message_id: int = 2) -> dict:
    return {
        "id": "cb1",
        "data": data,
        "from": {"id": OWNER},
        "message": {"message_id": message_id, "chat": {"id": OWNER}},
    }


def _message(text: str = "", **extra) -> dict:
    return {"message_id": 99, "chat": {"id": OWNER}, "from": {"id": OWNER}, "text": text, **extra}


def test_the_review_asks_the_header_then_one_message_per_event(db):
    _event(db, "Wake up", f"{DAY}T07:00:00")
    _event(db, "Gym", f"{DAY}T19:00:00")
    tg = FakeTelegram()

    assert review.send_review(db, tg, OWNER, DAY) is True

    assert tg.sent[0]["text"].startswith("🌙 <b>Evening review</b>")
    assert "How did today go?" in tg.sent[0]["text"]
    assert [b["text"] for b in tg.sent[0]["buttons"][0]] == ["Finish"]

    assert tg.sent[1]["text"] == "07:00 · <b>Wake up</b>"
    assert [b["text"] for b in tg.sent[1]["buttons"][0]] == ["✅ Done", "🟡 Partly", "❌ No"]
    assert tg.sent[2]["text"] == "19:00 · <b>Gym</b>"


def test_a_day_with_nothing_on_it_is_skipped_silently(db):
    tg = FakeTelegram()
    assert review.send_review(db, tg, OWNER, DAY) is False
    assert tg.sent == []


def test_a_tap_records_the_answer_and_settles_the_message_in_place(db):
    event = _event(db, "Wake up", f"{DAY}T07:00:00")
    _event(db, "Gym", f"{DAY}T19:00:00")
    tg = FakeTelegram()

    handlers.handle_callback(db, tg, _callback(f"ro:done:{event.id}", message_id=7), OWNER)

    assert review_svc.get_outcome(db, event.id).outcome == "done"
    assert tg.edited[-1]["message_id"] == 7
    assert tg.edited[-1]["text"] == "07:00 · <b>Wake up</b>\n✅ Done"
    # The settled card keeps one way forward: a note.
    assert [b["text"] for b in tg.edited[-1]["buttons"][0]] == ["📝 Note"]
    # Not everything is answered yet, so no score.
    assert not any("Effectiveness" in s["text"] for s in tg.sent)


def test_the_score_arrives_after_the_last_answer(db):
    first = _event(db, "Wake up", f"{DAY}T07:00:00")
    second = _event(db, "Gym", f"{DAY}T19:00:00")
    tg = FakeTelegram()

    handlers.handle_callback(db, tg, _callback(f"ro:done:{first.id}"), OWNER)
    handlers.handle_callback(db, tg, _callback(f"ro:partial:{second.id}"), OWNER)

    assert tg.sent[-1]["text"] == "📊 <b>Effectiveness — 75%</b>\n1/2 done, 1 partly"


def test_finish_sends_the_score_for_what_has_been_answered(db):
    first = _event(db, "Wake up", f"{DAY}T07:00:00")
    _event(db, "Gym", f"{DAY}T19:00:00")
    tg = FakeTelegram()

    handlers.handle_callback(db, tg, _callback(f"ro:done:{first.id}"), OWNER)
    handlers.handle_callback(db, tg, _callback(f"rv:{DAY}"), OWNER)

    assert tg.sent[-1] == {
        "chat_id": OWNER,
        "text": "📊 <b>Effectiveness — 100%</b>\n1/1 done",
        "buttons": None,
    }


def test_answering_later_still_works_and_updates_the_score(db):
    event = _event(db, "Wake up", f"{DAY}T07:00:00")
    tg = FakeTelegram()

    handlers.handle_callback(db, tg, _callback(f"ro:no:{event.id}"), OWNER)
    assert tg.sent[-1] == {
        "chat_id": OWNER,
        "text": "📊 <b>Effectiveness — 0%</b>\n0/1 done",
        "buttons": None,
    }

    handlers.handle_callback(db, tg, _callback(f"ro:done:{event.id}"), OWNER)
    assert review_svc.get_outcome(db, event.id).outcome == "done"
    assert tg.sent[-1]["text"].startswith("📊 <b>Effectiveness — 100%</b>")


# --- the note --------------------------------------------------------------


def test_the_note_prompt_carries_its_target_so_the_reply_needs_no_memory():
    text = review.copy.note_prompt("Wake up", "a1b2c3d4", 42)
    assert review.note_target(text) == ("a1b2c3d4", 42)
    assert review.note_target("just a message") is None


def test_a_reply_to_the_prompt_becomes_the_note_on_that_answer(db):
    event = _event(db, "Wake up", f"{DAY}T07:00:00")
    tg = FakeTelegram()

    handlers.handle_callback(db, tg, _callback(f"ro:partial:{event.id}", message_id=7), OWNER)
    handlers.handle_callback(db, tg, _callback(f"rn:{event.id}:7"), OWNER)
    prompt = tg.sent[-1]["text"]
    assert "Reply to this message" in prompt

    handlers.handle_message(
        db,
        tg,
        _message("woke at 07:20", reply_to_message={"message_id": 5, "text": prompt}),
        OWNER,
    )

    assert review_svc.get_outcome(db, event.id).note == "woke at 07:20"
    # The card itself shows it, so the answer stays readable in one place.
    assert tg.edited[-1]["text"] == "07:00 · <b>Wake up</b>\n🟡 Partly\n📝 woke at 07:20"
    assert tg.sent[-1]["text"] == "📝 Noted."


def test_a_reply_that_is_not_a_note_still_lands_in_the_inbox(db):
    from app.services import inbox as inbox_svc

    tg = FakeTelegram()
    handlers.handle_message(
        db,
        tg,
        _message("a thought", reply_to_message={"message_id": 5, "text": "something else"}),
        OWNER,
    )
    assert [i.text for i in inbox_svc.list_items(db)] == ["a thought"]


# --- /review ---------------------------------------------------------------


def test_slash_review_runs_todays_review_on_demand(db):
    today = datetime.now(ASTANA).strftime("%Y-%m-%d")
    _event(db, "Wake up", f"{today}T07:00:00")
    tg = FakeTelegram()

    handlers.handle_message(db, tg, _message("/review"), OWNER)

    assert tg.sent[0]["text"].startswith("🌙 <b>Evening review</b>")
    assert tg.sent[1]["text"] == "07:00 · <b>Wake up</b>"


def test_slash_review_on_an_empty_day_says_so_rather_than_nothing(db):
    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("/review"), OWNER)
    assert tg.sent[-1]["text"] == "Nothing was on the calendar today."


# --- the morning digest ----------------------------------------------------


def test_the_digest_carries_yesterdays_effectiveness():
    from app.bot import copy

    text = copy.digest(
        "2026-08-08",
        events=[],
        tasks=[],
        overdue=0,
        inbox=0,
        yesterday=summarize("2026-08-07", 6, ["done"] * 4 + ["partial", "no"]),
    )
    assert "📊 <b>Yesterday</b> · 4/6 done, 1 partly — 75%" in text


def test_the_digest_omits_the_line_for_a_day_he_never_reviewed():
    from app.bot import copy

    text = copy.digest(
        "2026-08-08", [], [], 0, 0, yesterday=summarize("2026-08-07", 3, [])
    )
    assert "Yesterday" not in text
    assert copy.digest("2026-08-08", [], [], 0, 0) == text


# --- the API ---------------------------------------------------------------


def test_the_site_can_read_a_day_score_and_the_strip(client, auth, db):
    event = _event(db, "Wake up", f"{DAY}T07:00:00")
    review_svc.record_outcome(db, event.id, "done")

    day = client.get(f"/api/calendar/review/{DAY}", headers=auth)
    assert day.status_code == 200
    assert day.json()["percent"] == 100

    summary = client.get("/api/calendar/review/summary?days=7", headers=auth)
    assert summary.status_code == 200
    body = summary.json()
    assert len(body["days"]) == 7
    assert body["days"][-1]["day"] == datetime.now(ASTANA).strftime("%Y-%m-%d")
    assert "percent" in body["yesterday"]


def test_the_review_time_is_editable_from_the_calendar_page(client, auth):
    # The payload carries both bot times; the weekly one is exercised in
    # tests/test_weekly.py.
    assert client.get("/api/calendar/review/settings", headers=auth).json()[
        "review_time"
    ] == "21:30"

    saved = client.put(
        "/api/calendar/review/settings", json={"review_time": "22:15"}, headers=auth
    )
    assert saved.status_code == 200
    assert saved.json()["review_time"] == "22:15"
    assert client.get("/api/calendar/review/settings", headers=auth).json()[
        "review_time"
    ] == "22:15"

    bad = client.put(
        "/api/calendar/review/settings", json={"review_time": "99:99"}, headers=auth
    )
    assert bad.status_code == 422


def test_the_review_endpoints_are_admin_only(client):
    assert client.get(f"/api/calendar/review/{DAY}").status_code in (401, 403)
    assert client.get("/api/calendar/review/summary").status_code in (401, 403)
    assert client.get("/api/calendar/review/settings").status_code in (401, 403)


def test_an_outcome_can_be_recorded_over_http_too(client, auth, db):
    event = _event(db, "Wake up", f"{DAY}T07:00:00")

    res = client.put(
        f"/api/calendar/events/{event.id}/outcome",
        json={"outcome": "partial", "note": "late"},
        headers=auth,
    )
    assert res.status_code == 200
    assert res.json()["outcome"] == "partial"
    assert review_svc.get_outcome(db, event.id).note == "late"

    assert (
        client.put(
            f"/api/calendar/events/{event.id}/outcome", json={"outcome": "maybe"}, headers=auth
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/calendar/events/nope/outcome", json={"outcome": "done"}, headers=auth
        ).status_code
        == 404
    )
