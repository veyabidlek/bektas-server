"""Sleep ingestion: what the shortcut may send, and what the server makes of it.

The aggregation half is pure, so most of this needs no database — the same
shape `test_assistant.py` has. What is being defended here is mostly
*tolerance*: the POST is filled in by a hand-built Apple Shortcut with no
console, so every test that looks like it is about string spelling is really
about a morning that would otherwise silently record nothing.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.dependencies import INGEST_TOKEN_ENV
from app.schemas.sleep import SleepIngestIn
from app.services import assistant as assistant_svc
from app.services import assistant_format as fmt
from app.services import sleep as svc
from app.services import sleep_night as night

ASTANA = ZoneInfo("Asia/Almaty")
TOKEN = "shortcut-token-not-the-real-one"


def seg(start: str, end: str, stage: str = "Deep") -> dict:
    return {"start": start, "end": end, "stage": stage}


def aggregate(raw: list[dict], date: str | None = None):
    segments, unrecognized, _ = svc.parse_segments(SleepIngestIn(segments=raw, date=date))
    return night.aggregate(segments, date), unrecognized


# --- timestamps -----------------------------------------------------------


def test_an_offset_is_taken_at_its_word():
    assert night.parse_dt("2026-08-11T07:31:00+05:00") == datetime(
        2026, 8, 11, 7, 31, tzinfo=ASTANA
    )
    # Z is an offset too, and is not the same wall clock.
    assert night.parse_dt("2026-08-11T02:31:00Z").astimezone(ASTANA).hour == 7


def test_a_timestamp_without_an_offset_is_his_local_time():
    """Almaty, not UTC — guessing UTC would be five hours wrong every night."""
    assert night.parse_dt("2026-08-11T07:31:00").utcoffset() == timedelta(hours=5)
    assert night.parse_dt("2026-08-11 07:31:00").astimezone(ASTANA).hour == 7


def test_the_space_separated_shape_shortcuts_emit_is_accepted():
    assert night.parse_dt("2026-08-11 23:05:00") == datetime(
        2026, 8, 11, 23, 5, tzinfo=ASTANA
    )


def test_an_unreadable_timestamp_names_the_value_it_choked_on():
    """The shortcut's author has no console — the message is the whole report."""
    with pytest.raises(ValueError, match="yesterday evening"):
        night.parse_dt("yesterday evening")
    with pytest.raises(ValueError, match="empty"):
        night.parse_dt("   ")


# --- stage names ----------------------------------------------------------


def test_apples_stage_names_are_read_however_they_are_spaced_and_cased():
    for raw in ("In Bed", "InBed", "in_bed", "  in bed  ", "IN BED"):
        assert night.normalize_stage(raw) == ("in_bed", True), raw
    for raw in ("Asleep", "AsleepUnspecified", "asleep unspecified"):
        assert night.normalize_stage(raw) == ("asleep", True), raw
    assert night.normalize_stage("AsleepCore") == ("core", True)
    assert night.normalize_stage("Core") == ("core", True)
    assert night.normalize_stage("AsleepDeep") == ("deep", True)
    assert night.normalize_stage("deep") == ("deep", True)
    assert night.normalize_stage("AsleepREM") == ("rem", True)
    assert night.normalize_stage("rem") == ("rem", True)
    assert night.normalize_stage("Awake") == ("awake", True)


def test_the_raw_healthkit_enum_name_is_read_too():
    assert night.normalize_stage("HKCategoryValueSleepAnalysisAsleepDeep") == ("deep", True)


def test_an_unknown_stage_counts_as_sleep_and_is_reported_back():
    """Conservative on the number, loud in the response — a night that arrived
    beats a night rejected on a spelling, but the recipe still has to be fixed."""
    assert night.normalize_stage("LightSleep") == ("asleep", False)

    result, unrecognized = aggregate(
        [seg("2026-08-11T00:00:00+05:00", "2026-08-11T06:00:00+05:00", "LightSleep")]
    )
    assert result.asleep_minutes == 360
    assert unrecognized == ["LightSleep"]


def test_the_same_unknown_stage_is_only_reported_once():
    _, unrecognized = aggregate(
        [
            seg("2026-08-11T00:00:00+05:00", "2026-08-11T01:00:00+05:00", "Snoozing"),
            seg("2026-08-11T01:00:00+05:00", "2026-08-11T02:00:00+05:00", "Snoozing"),
        ]
    )
    assert unrecognized == ["Snoozing"]


# --- the night ------------------------------------------------------------


def test_a_night_belongs_to_the_morning_he_woke_up():
    """23:00 → 07:00 is filed under the 07:00 day, not the 23:00 one."""
    result, _ = aggregate(
        [
            seg("2026-08-10T23:00:00+05:00", "2026-08-11T03:00:00+05:00", "Core"),
            seg("2026-08-11T03:00:00+05:00", "2026-08-11T07:00:00+05:00", "Deep"),
        ]
    )
    assert result.date == "2026-08-11"
    assert result.bedtime == "2026-08-10T23:00:00+05:00"
    assert result.wake_time == "2026-08-11T07:00:00+05:00"
    assert result.asleep_minutes == 480


def test_the_morning_is_his_morning_not_utcs():
    """A 01:00 Almaty wake-up is still 20:00 the day before in UTC."""
    result, _ = aggregate(
        [seg("2026-08-10T21:00:00+05:00", "2026-08-11T01:00:00+05:00", "Deep")]
    )
    assert result.date == "2026-08-11"


def test_overlapping_segments_are_merged_not_summed():
    """Apple Health holds the watch's night and the phone's night at once."""
    result, _ = aggregate(
        [
            seg("2026-08-11T00:00:00+05:00", "2026-08-11T04:00:00+05:00", "Core"),
            seg("2026-08-11T02:00:00+05:00", "2026-08-11T06:00:00+05:00", "Core"),
        ]
    )
    assert result.asleep_minutes == 360  # not 480
    assert result.core_minutes == 360


def test_an_exact_duplicate_is_counted_once():
    one = seg("2026-08-11T00:00:00+05:00", "2026-08-11T06:30:00+05:00", "Asleep")
    result, _ = aggregate([one, dict(one)])
    assert result.asleep_minutes == 390


def test_touching_segments_do_not_double_count_the_boundary():
    result, _ = aggregate(
        [
            seg("2026-08-11T00:00:00+05:00", "2026-08-11T01:00:00+05:00", "Core"),
            seg("2026-08-11T01:00:00+05:00", "2026-08-11T02:00:00+05:00", "Deep"),
        ]
    )
    assert result.asleep_minutes == 120
    assert result.core_minutes == 60 and result.deep_minutes == 60


def test_awake_and_in_bed_are_not_sleep():
    result, _ = aggregate(
        [
            seg("2026-08-10T23:00:00+05:00", "2026-08-11T07:30:00+05:00", "In Bed"),
            seg("2026-08-10T23:30:00+05:00", "2026-08-11T07:00:00+05:00", "Core"),
            seg("2026-08-11T03:00:00+05:00", "2026-08-11T03:20:00+05:00", "Awake"),
        ]
    )
    assert result.in_bed_minutes == 510
    assert result.awake_minutes == 20
    # The awake stretch sits inside the core block; the band reported both, and
    # only the sleep union is asleep_minutes.
    assert result.asleep_minutes == 450
    assert result.bedtime == "2026-08-10T23:30:00+05:00"


def test_a_stage_that_was_never_reported_is_null_not_zero():
    """"The band did not measure REM" is not "he got no REM"."""
    result, _ = aggregate(
        [seg("2026-08-11T00:00:00+05:00", "2026-08-11T06:00:00+05:00", "Asleep")]
    )
    assert result.rem_minutes is None
    assert result.deep_minutes is None
    assert result.core_minutes is None
    assert result.in_bed_minutes is None
    assert result.awake_minutes is None
    assert result.asleep_minutes == 360


def test_a_segment_longer_than_a_day_is_garbage_and_is_dropped():
    result, _ = aggregate(
        [
            seg("2026-08-01T00:00:00+05:00", "2026-08-11T07:00:00+05:00", "Asleep"),
            seg("2026-08-11T00:00:00+05:00", "2026-08-11T06:00:00+05:00", "Deep"),
        ]
    )
    assert result.asleep_minutes == 360
    assert result.date == "2026-08-11"


def test_a_backwards_or_empty_segment_contributes_nothing():
    result, _ = aggregate(
        [
            seg("2026-08-11T06:00:00+05:00", "2026-08-11T00:00:00+05:00", "Deep"),
            seg("2026-08-11T01:00:00+05:00", "2026-08-11T01:00:00+05:00", "Deep"),
            seg("2026-08-11T00:00:00+05:00", "2026-08-11T05:00:00+05:00", "Core"),
        ]
    )
    assert result.asleep_minutes == 300
    assert result.deep_minutes is None


def test_nothing_usable_is_no_night_at_all():
    assert night.aggregate([]) is None
    result, _ = aggregate([seg("2026-08-11T06:00:00+05:00", "2026-08-11T00:00:00+05:00")])
    assert result is None


def test_an_explicit_date_overrides_the_computed_one():
    """For backfilling an old export; the daily run should never send it."""
    result, _ = aggregate(
        [seg("2026-08-11T00:00:00+05:00", "2026-08-11T06:00:00+05:00", "Deep")],
        date="2026-01-05",
    )
    assert result.date == "2026-01-05"


# --- auth -----------------------------------------------------------------

NIGHT = {
    "segments": [
        seg("2026-08-10T23:00:00+05:00", "2026-08-11T03:00:00+05:00", "Core"),
        seg("2026-08-11T03:00:00+05:00", "2026-08-11T07:00:00+05:00", "Deep"),
    ]
}


def test_without_the_env_var_the_endpoint_says_which_one_is_missing(client, monkeypatch):
    """503, not 401: nothing is broken and no token would have worked."""
    monkeypatch.delenv(INGEST_TOKEN_ENV, raising=False)
    res = client.post("/api/health/sleep", json=NIGHT, headers={"Authorization": "Bearer x"})
    assert res.status_code == 503
    assert INGEST_TOKEN_ENV in res.json()["detail"]


def test_a_wrong_token_is_rejected(client, monkeypatch):
    monkeypatch.setenv(INGEST_TOKEN_ENV, TOKEN)
    assert client.post("/api/health/sleep", json=NIGHT).status_code == 401
    assert (
        client.post(
            "/api/health/sleep", json=NIGHT, headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    # An almost-right one, since the comparison is constant-time.
    assert (
        client.post(
            "/api/health/sleep", json=NIGHT, headers={"Authorization": f"Bearer {TOKEN}x"}
        ).status_code
        == 401
    )


def test_the_right_token_is_let_in(client, monkeypatch):
    monkeypatch.setenv(INGEST_TOKEN_ENV, TOKEN)
    res = client.post(
        "/api/health/sleep", json=NIGHT, headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert res.status_code == 200, res.text


def test_the_admin_session_is_not_the_ingest_credential(client, auth, monkeypatch):
    """Deliberately separate: the shortcut's token writes health and nothing else."""
    monkeypatch.setenv(INGEST_TOKEN_ENV, TOKEN)
    assert client.post("/api/health/sleep", json=NIGHT, headers=auth).status_code == 401


# --- the endpoints --------------------------------------------------------


@pytest.fixture()
def ingest(client, monkeypatch):
    monkeypatch.setenv(INGEST_TOKEN_ENV, TOKEN)

    def post(body):
        return client.post(
            "/api/health/sleep", json=body, headers={"Authorization": f"Bearer {TOKEN}"}
        )

    return post


def test_the_response_is_the_stored_night_plus_what_was_not_understood(ingest):
    res = ingest(
        {
            "segments": [
                seg("2026-08-10T23:00:00+05:00", "2026-08-11T03:00:00+05:00", "Core"),
                seg("2026-08-11T03:00:00+05:00", "2026-08-11T06:00:00+05:00", "AsleepDeep"),
                seg("2026-08-11T06:00:00+05:00", "2026-08-11T07:00:00+05:00", "Dozing"),
            ]
        }
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["date"] == "2026-08-11"
    assert body["asleep_minutes"] == 480
    assert body["core_minutes"] == 240 and body["deep_minutes"] == 180
    assert body["bedtime"] == "2026-08-10T23:00:00+05:00"
    assert body["wake_time"] == "2026-08-11T07:00:00+05:00"
    assert body["unrecognized_stages"] == ["Dozing"]


def test_healthkits_own_field_names_are_accepted(ingest):
    """A Shortcut that passes a sample straight through sends these."""
    res = ingest(
        {
            "segments": [
                {
                    "startDate": "2026-08-10 23:00:00",
                    "endDate": "2026-08-11 07:00:00",
                    "value": "AsleepCore",
                }
            ]
        }
    )
    assert res.status_code == 200, res.text
    assert res.json()["core_minutes"] == 480


def test_an_unreadable_timestamp_is_a_422_that_names_it(ingest):
    res = ingest({"segments": [seg("2026-08-10T23:00:00+05:00", "later that night")]})
    assert res.status_code == 422
    assert "later that night" in res.text


def test_an_upload_with_nothing_usable_is_a_422(ingest):
    assert ingest({"segments": []}).status_code == 422


def test_running_the_shortcut_twice_replaces_the_night(ingest, client, auth):
    ingest(NIGHT)
    ingest(
        {
            "segments": [
                seg("2026-08-10T23:00:00+05:00", "2026-08-11T05:00:00+05:00", "Deep")
            ]
        }
    )
    nights = client.get("/api/health/sleep", headers=auth).json()["nights"]
    assert len(nights) == 1
    assert nights[0]["asleep_minutes"] == 360
    assert nights[0]["core_minutes"] is None


def test_the_raw_segments_are_kept_for_a_later_re_analysis(ingest, db):
    from app.models.sleep import SleepNight

    ingest(NIGHT)
    row = db.query(SleepNight).filter(SleepNight.date == "2026-08-11").first()
    assert len(row.segments) == 2
    assert row.segments[0]["stage"] == "core" and row.segments[0]["raw_stage"] == "Core"


def test_reading_the_nights_back_needs_the_admin_session(client, ingest):
    ingest(NIGHT)
    assert client.get("/api/health/sleep").status_code == 401
    assert (
        client.get(
            "/api/health/sleep", headers={"Authorization": f"Bearer {TOKEN}"}
        ).status_code
        == 401
    )


def test_the_nights_come_back_newest_first_in_the_clients_shape(ingest, client, auth):
    for day in ("2026-08-09", "2026-08-11", "2026-08-10"):
        ingest({"segments": [seg(f"{day}T00:00:00+05:00", f"{day}T06:00:00+05:00", "Deep")]})

    body = client.get("/api/health/sleep", headers=auth).json()
    assert [n["date"] for n in body["nights"]] == ["2026-08-11", "2026-08-10", "2026-08-09"]
    assert set(body["nights"][0]) == {
        "date",
        "in_bed_minutes",
        "asleep_minutes",
        "deep_minutes",
        "rem_minutes",
        "core_minutes",
        "awake_minutes",
        "bedtime",
        "wake_time",
    }


def test_days_narrows_the_window_and_is_capped(ingest, client, auth):
    for day in ("2026-08-09", "2026-08-10", "2026-08-11"):
        ingest({"segments": [seg(f"{day}T00:00:00+05:00", f"{day}T06:00:00+05:00", "Deep")]})

    assert len(client.get("/api/health/sleep?days=2", headers=auth).json()["nights"]) == 2
    assert client.get("/api/health/sleep?days=0", headers=auth).status_code == 422
    assert client.get("/api/health/sleep?days=400", headers=auth).status_code == 422


# --- what the assistant is told -------------------------------------------


def test_a_duration_is_padded_so_two_nights_line_up():
    assert fmt.hours_minutes(400) == "6h 40m"
    assert fmt.hours_minutes(65) == "1h 05m"
    assert fmt.hours_minutes(45) == "45m"
    assert fmt.hours_minutes(120) == "2h 00m"
    # The focus-time wording is untouched by the padded variant.
    assert fmt.minutes(120) == "2h"


def test_the_latest_night_reads_as_a_sentence():
    assert (
        fmt.sleep_line("2026-08-11", 400, 65, "2026-08-11T00:12:00+05:00",
                       "2026-08-11T07:31:00+05:00")
        == "2026-08-11: 6h 40m asleep · 1h 05m deep · bed 00:12 → up 07:31"
    )


def test_an_unreported_stage_is_left_out_rather_than_printed_as_zero():
    line = fmt.sleep_line("2026-08-11", 400, None, None, None)
    assert line == "2026-08-11: 6h 40m asleep"


def test_the_average_counts_only_the_nights_that_were_recorded():
    """A band on the charger is not a zero-sleep night."""
    assert fmt.sleep_average([420, 400]) == 410
    assert fmt.sleep_average([]) is None
    assert "2 night(s) recorded, averaging 6h 50m asleep" == fmt.sleep_average_line([420, 400])


def test_the_shortfall_line_appears_only_below_the_seven_hour_average():
    assert fmt.sleep_shortfall([]) is None
    assert fmt.sleep_shortfall([420, 430]) is None
    assert fmt.sleep_shortfall([420]) is None  # exactly the target is not a shortfall
    line = fmt.sleep_shortfall([350] * 7)
    assert "averaging 5h 50m over the last 7 nights" in line


def test_the_snapshot_carries_the_week_and_names_the_shortfall(db, ingest):
    for day, hours in (("2026-08-09", 5), ("2026-08-10", 6), ("2026-08-11", 6)):
        ingest(
            {
                "segments": [
                    seg(
                        f"{day}T00:12:00+05:00",
                        f"{day}T{0 + hours:02d}:12:00+05:00",
                        "Deep",
                    )
                ]
            }
        )

    context = assistant_svc.build_context(db, datetime(2026, 8, 11, 10, 0, tzinfo=ASTANA))
    assert "SLEEP (last 7 recorded nights)" in context
    assert "Latest night — 2026-08-11: 6h 00m asleep · 6h 00m deep" in context
    assert "3 night(s) recorded, averaging 5h 40m asleep" in context
    assert "averaging 5h 40m over the last 3 nights" in context


def test_with_no_band_data_the_snapshot_says_so_rather_than_going_quiet(db):
    """The model must not guess how he slept — that is the whole point of this
    section existing rather than being left out when empty."""
    context = assistant_svc.build_context(db, datetime(2026, 8, 11, 10, 0, tzinfo=ASTANA))
    assert "SLEEP" in context
    assert "no sleep data yet" in context


def test_a_well_slept_week_gets_no_shortfall_line(db, ingest):
    """Nothing to raise unprompted, so the line is simply absent."""
    ingest({"segments": [seg("2026-08-10T23:00:00+05:00", "2026-08-11T07:00:00+05:00")]})
    ingest({"segments": [seg("2026-08-11T23:00:00+05:00", "2026-08-12T07:30:00+05:00")]})

    context = assistant_svc.build_context(db, datetime(2026, 8, 12, 10, 0, tzinfo=ASTANA))
    assert "2 night(s) recorded, averaging 8h 15m asleep" in context
    assert "BELOW TARGET" not in context
