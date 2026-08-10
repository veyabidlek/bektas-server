"""The personal assistant: what it can see, and what it does when it cannot answer.

The formatting half is pure, so most of this needs no database at all. The
model is never called for real — `llm.chat` is replaced, exactly the way the
weekly digest's suite does it. The two surfaces (the endpoint and `/a`) are
next door in `test_assistant_api.py`.
"""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from app.schemas.calendar import CalendarEventCreate
from app.schemas.task import TaskCreate
from app.services import assistant as svc
from app.services import assistant_format as fmt
from app.services import calendar as calendar_svc
from app.services import habits as habits_svc
from app.services import inbox as inbox_svc
from app.services import llm
from app.services import tasks as tasks_svc

ASTANA = ZoneInfo("Asia/Almaty")
NOW = datetime(2026, 8, 12, 10, 0, tzinfo=ASTANA)
TODAY = "2026-08-12"


@dataclass
class FakeTask:
    title: str
    due_at: str | None


# --- the pure formatting layer -------------------------------------------


def test_a_section_that_is_empty_says_so_rather_than_disappearing():
    """A missing heading would read as missing data the model should hedge about."""
    assert fmt.section("TODAY", []) == "TODAY\n- (none)"
    assert fmt.section("TODAY", [], empty="nothing scheduled").endswith("nothing scheduled")
    assert fmt.section("TODAY", ["a", "b"]) == "TODAY\n- a\n- b"


def test_an_event_reads_as_its_almaty_clock_time():
    assert fmt.event_line("2026-08-12T09:00:00+05:00", "Dentist") == "09:00 · Dentist"
    assert fmt.event_line("2026-08-12", "Eid") == "all-day · Eid"
    assert fmt.event_line("2026-08-12T09:00:00+05:00", "Eid", all_day=True) == "all-day · Eid"


def test_lateness_is_on_the_left_where_it_cannot_be_skimmed_past():
    assert fmt.task_line("fix landing", "2026-07-31", TODAY).startswith("[OVERDUE 12d] ")
    assert fmt.task_line("call mum", TODAY, TODAY).startswith("[TODAY] ")
    assert fmt.task_line("later", "2026-09-01", TODAY) == "later — due 2026-09-01"
    assert fmt.task_line("someday", None, TODAY) == "someday — no due date"
    assert fmt.task_line("call", f"{TODAY}T14:30:00+05:00", TODAY).endswith("due 2026-08-12 14:30")


def test_open_tasks_are_ordered_overdue_then_today_then_the_rest():
    tasks = [
        FakeTask("someday", None),
        FakeTask("next month", "2026-09-01"),
        FakeTask("today", TODAY),
        FakeTask("late", "2026-08-10"),
        FakeTask("very late", "2026-07-31"),
    ]
    assert [t.title for t in fmt.order_tasks(tasks, TODAY)] == [
        "very late",
        "late",
        "today",
        "next month",
        "someday",
    ]


def test_the_task_list_is_capped():
    tasks = [FakeTask(f"t{n}", None) for n in range(40)]
    assert len(fmt.order_tasks(tasks, TODAY)) == fmt.TASK_LIMIT == 25


def test_the_overdue_pile_names_its_oldest_item():
    """"5 overdue" is a statistic; "fix landing, 12 days late" is actionable."""
    tasks = [
        FakeTask("fix landing", "2026-07-31"),
        FakeTask("email", "2026-08-11"),
        FakeTask("today", TODAY),
    ]
    assert fmt.overdue_summary(tasks, TODAY) == '2 overdue, oldest 12 days: "fix landing"'
    assert fmt.overdue_summary([FakeTask("t", TODAY)], TODAY) == "none overdue"


def test_a_habit_carries_its_week_not_just_todays_tick():
    week = fmt.recent_days(TODAY)
    done = {"2026-08-08": True, "2026-08-11": True}
    assert fmt.week_done(done, week) == 2
    assert (
        fmt.habit_line("Quran", "islam", False, 2)
        == "Quran [islam]: PENDING today · 2/7 days this week"
    )
    assert fmt.habit_line("Run", None, True, 7) == "Run: done today · 7/7 days this week"


def test_the_seven_day_window_ends_today_inclusive():
    week = fmt.recent_days(TODAY)
    assert len(week) == 7
    assert week[0] == "2026-08-06" and week[-1] == TODAY


def test_focus_time_is_stated_against_the_week_before():
    assert fmt.minutes(0) == "0m"
    assert fmt.minutes(45) == "45m"
    assert fmt.minutes(200) == "3h 20m"
    assert fmt.minutes(120) == "2h"

    assert "down 60% vs the week before" in fmt.focus_line(192, 480)
    assert "up 50% vs the week before" in fmt.focus_line(180, 120)
    assert "level with the week before" in fmt.focus_line(120, 120)
    assert "nothing the week before" in fmt.focus_line(0, 0)
    assert "down to nothing" in fmt.focus_line(0, 300)


def test_focus_minutes_are_summed_off_the_existing_daily_map():
    daily = {"2026-08-12": 50, "2026-08-11": 25, "2026-07-01": 999}
    assert fmt.sum_days(daily, fmt.recent_days(TODAY)) == 75


# --- the snapshot ---------------------------------------------------------


def _context(db):
    return svc.build_context(db, NOW)


def test_the_snapshot_labels_every_section_it_promises(db):
    context = _context(db)
    for heading in (
        "NOW",
        "TODAY'S EVENTS",
        "TOMORROW'S EVENTS",
        "OPEN TASKS",
        "HABITS",
        "FOCUS TIME (pomodoro)",
        "CURRENTLY READING",
        "INBOX",
    ):
        assert heading in context, heading


def test_an_empty_app_reads_as_empty_rather_than_as_silence(db):
    context = _context(db)
    assert "nothing scheduled" in context
    assert "nothing open" in context
    assert "none overdue" in context
    assert "no habits tracked" in context
    assert "no book in progress" in context
    assert "0 captured item(s)" in context


def test_todays_and_tomorrows_events_land_in_their_own_sections(db):
    calendar_svc.create_event(
        db, CalendarEventCreate(title="Dentist", starts_at=f"{TODAY}T09:00:00")
    )
    calendar_svc.create_event(
        db, CalendarEventCreate(title="Flight", starts_at="2026-08-13T18:00:00")
    )
    context = _context(db)

    today_block = context.split("TODAY'S EVENTS")[1].split("TOMORROW'S EVENTS")[0]
    tomorrow_block = context.split("TOMORROW'S EVENTS")[1].split("OPEN TASKS")[0]

    assert "09:00 · Dentist" in today_block and "Flight" not in today_block
    assert "18:00 · Flight" in tomorrow_block and "Dentist" not in tomorrow_block


def test_the_overdue_pile_reaches_the_snapshot_with_its_age(db):
    tasks_svc.create_task(db, TaskCreate(title="fix landing", due_at="2026-07-31"))
    tasks_svc.create_task(db, TaskCreate(title="call mum", due_at=TODAY))
    context = _context(db)

    assert "[OVERDUE 12d] fix landing" in context
    assert "[TODAY] call mum" in context
    assert 'Overdue: 1 overdue, oldest 12 days: "fix landing"' in context
    # Overdue is listed before what is merely due today.
    assert context.index("fix landing") < context.index("call mum")


def test_a_finished_task_is_not_an_open_one(db):
    task = tasks_svc.create_task(db, TaskCreate(title="shipped it", due_at="2026-07-31"))
    tasks_svc.set_done(db, task, True)
    assert "shipped it" not in _context(db)
    assert "none overdue" in _context(db)


def test_a_habit_appears_with_its_category_and_its_week(db):
    habits_svc.create_habit(db, "quran", "Quran", "📖", "green", category="islam")
    habits_svc.toggle_habit(db, "quran", TODAY)
    habits_svc.toggle_habit(db, "quran", "2026-08-10")

    assert "Quran [islam]: done today · 2/7 days this week" in _context(db)


def test_a_neglected_habit_says_pending_and_shows_the_gap(db):
    habits_svc.create_habit(db, "run", "Run", "🏃", "red")
    assert "Run: PENDING today · 0/7 days this week" in _context(db)


def test_an_archived_habit_is_not_something_to_be_scolded_about(db):
    habits_svc.create_habit(db, "old", "Old habit", "🕯", "grey")
    habits_svc.archive_habit(db, "old", True)
    assert "Old habit" not in _context(db)


def test_focus_time_compares_the_two_windows(db):
    from app.models.pomodoro import PomodoroSession, Project

    db.add(Project(id="p1", name="Work", color="blue"))
    db.add(PomodoroSession(id="s1", project_id="p1", description="a",
                           started_at=f"{TODAY}T06:00:00+00:00", duration_minutes=60))
    db.add(PomodoroSession(id="s2", project_id="p1", description="b",
                           started_at="2026-08-03T06:00:00+00:00", duration_minutes=120))
    db.commit()

    assert "1h in the last 7 days, 2h the 7 before — down 50%" in _context(db)


def test_a_book_in_progress_is_what_he_is_reading(db):
    from app.models.reading import ReadingItem

    db.add(ReadingItem(title="Deep Work", author="Cal Newport", status="in_progress",
                       created_at="2026-08-01T00:00:00+05:00"))
    db.add(ReadingItem(title="Someday", status="not_started",
                       created_at="2026-08-01T00:00:00+05:00"))
    db.commit()

    context = _context(db)
    assert "Deep Work — Cal Newport" in context
    assert "Someday" not in context


def test_the_open_inbox_is_counted(db):
    inbox_svc.create_item(db, "a thought")
    inbox_svc.create_item(db, "another")
    assert "2 captured item(s)" in _context(db)


# --- the prompt -----------------------------------------------------------


def test_a_question_without_history_is_just_the_question():
    assert svc.build_prompt("what's left today?") == "Question: what's left today?"


def test_the_last_few_turns_ride_along_for_pronouns_to_point_at():
    history = [{"role": "user", "content": "what's on today?"},
               {"role": "assistant", "content": "Dentist at 09:00."}]
    prompt = svc.build_prompt("and tomorrow?", history)
    assert "User: what's on today?" in prompt
    assert "Assistant: Dentist at 09:00." in prompt
    assert prompt.endswith("Question: and tomorrow?")


def test_only_the_last_ten_turns_are_carried():
    history = [{"role": "user", "content": f"turn {n}"} for n in range(30)]
    prompt = svc.build_prompt("now what?", history)
    assert "turn 29" in prompt and "turn 20" in prompt and "turn 19" not in prompt


def test_the_prompt_is_told_to_be_an_honest_coach_grounded_in_the_numbers():
    assert "personal assistant inside his own productivity app" in svc.SYSTEM
    assert "never invent events, tasks or numbers" in svc.SYSTEM
    assert "Reply in the language the question was asked in" in svc.SYSTEM
    assert "honest and direct, like a good coach" in svc.SYSTEM
    assert "name the specific habit/task" in svc.SYSTEM
    assert "Never flatter" in svc.SYSTEM


# --- answering ------------------------------------------------------------


def test_without_a_key_there_is_no_answer_and_no_exception(db, monkeypatch):
    """Optional by construction — the same rule the digest's paragraph follows."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert svc.answer(db, "what's left today?") is None


def test_a_model_failure_is_a_missing_answer_not_a_crash(db, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    def explode(*args, **kwargs):
        raise OSError("connection reset")

    monkeypatch.setattr("urllib.request.urlopen", explode)
    assert svc.answer(db, "what's left today?") is None


def test_an_empty_completion_is_no_answer(db, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "   ")
    assert svc.answer(db, "anything?") is None


def test_an_empty_question_never_reaches_the_model(db, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    called = []
    monkeypatch.setattr(llm, "chat", lambda *a, **k: called.append(a) or "hi")
    assert svc.answer(db, "   ") is None
    assert called == []


def test_the_context_is_what_the_model_is_given(db, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    habits_svc.create_habit(db, "quran", "Quran", "📖", "green", category="islam")
    seen = {}

    def fake_chat(system, user, **kwargs):
        seen["system"] = system
        seen["user"] = user
        seen["max_tokens"] = kwargs.get("max_tokens")
        return "You skipped Quran every day this week."

    monkeypatch.setattr(llm, "chat", fake_chat)

    assert svc.answer(db, "how are my habits?") == "You skipped Quran every day this week."
    assert "CONTEXT" in seen["system"]
    assert "Quran [islam]" in seen["system"]
    assert seen["user"] == "Question: how are my habits?"
    # DeepSeek's reasoning trace eats the budget — a tight one returns nothing.
    assert seen["max_tokens"] >= 2000
