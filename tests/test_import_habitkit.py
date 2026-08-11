"""The pure half of the HabitKit importer: date math, goal extraction, and
the day-folding rules that decide what a stored row will claim."""

from scripts.import_habitkit import (
    completion_local_date,
    day_rows,
    habit_created_date,
    pick_interval,
    target_from_interval,
)


def test_habit_created_date_lands_on_the_almaty_day():
    # 21:19 UTC is already the next day in Almaty (+5).
    assert habit_created_date("2025-01-06T21:19:22.655831Z") == "2025-01-07"


def test_completion_uses_its_own_recorded_offset():
    c = {"date": "2025-01-05T19:36:23.848155Z", "timezoneOffsetInMinutes": 300}
    assert completion_local_date(c) == "2025-01-06"
    c["timezoneOffsetInMinutes"] = 0
    assert completion_local_date(c) == "2025-01-05"


def test_open_interval_wins_over_a_closed_one():
    closed = {"startDate": "2025-01-01", "endDate": "2025-02-01",
              "requiredNumberOfCompletionsPerDay": 5, "type": "day"}
    open_ = {"startDate": "2025-02-01", "endDate": None,
             "requiredNumberOfCompletionsPerDay": 2, "type": "day"}
    assert pick_interval([closed, open_]) is open_


def test_week_goals_import_as_plain_habits():
    assert target_from_interval({"type": "week", "requiredNumberOfCompletionsPerDay": 30}) is None
    assert target_from_interval({"type": "day", "requiredNumberOfCompletionsPerDay": 2}) == 2
    assert target_from_interval({"type": "day", "requiredNumberOfCompletionsPerDay": 1}) is None
    assert target_from_interval(None) is None


def test_day_rows_fold_duplicates_to_the_larger_count():
    completions = [
        {"date": "2025-01-30T05:00:00Z", "timezoneOffsetInMinutes": 300, "amountOfCompletions": 1},
        {"date": "2025-01-30T15:00:00Z", "timezoneOffsetInMinutes": 300, "amountOfCompletions": 2},
    ]
    assert day_rows(completions, target=2) == {"2025-01-30": ("done", 2)}


def test_day_rows_on_a_counted_habit_split_done_and_partial():
    completions = [
        {"date": "2025-01-30T05:00:00Z", "timezoneOffsetInMinutes": 300, "amountOfCompletions": 1},
        {"date": "2025-01-31T05:00:00Z", "timezoneOffsetInMinutes": 300, "amountOfCompletions": 2},
    ]
    assert day_rows(completions, target=2) == {
        "2025-01-30": ("partial", 1),
        "2025-01-31": ("done", 2),
    }


def test_day_rows_on_a_plain_habit_store_no_amount_and_zero_means_ticked():
    completions = [
        {"date": "2025-01-30T05:00:00Z", "timezoneOffsetInMinutes": 300, "amountOfCompletions": 0},
    ]
    assert day_rows(completions, target=None) == {"2025-01-30": ("done", None)}
