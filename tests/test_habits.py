"""Habits: the three day-states, what the old boolean toggle still means, and auth.

The compatibility promise this suite exists to defend: `completed_days` used to
be `{date: true}` and clients truthy-check it, so a fully-done day must keep
serializing as the JSON boolean `true` even now that "partial" is a value.
"""

import pytest


@pytest.fixture()
def habit(client, auth):
    res = client.post(
        "/api/habits",
        headers=auth,
        json={"id": "quran", "name": "Quran", "emoji": "📖", "color": "#0a0"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _days(client, habit_id="quran"):
    listing = client.get("/api/habits").json()
    return next(h for h in listing if h["id"] == habit_id)["completed_days"]


def test_mark_round_trips_done_partial_and_none(client, auth, habit):
    done = client.post(
        "/api/habits/quran/mark",
        headers=auth,
        json={"date": "2026-08-10", "state": "done"},
    )
    assert done.status_code == 200, done.text
    assert done.json() == {"date": "2026-08-10", "state": "done"}
    assert _days(client)["2026-08-10"] is True

    # Re-marking the same day is a write, not a flip — the swipe UI can land on
    # the same state twice without undoing itself.
    partial = client.post(
        "/api/habits/quran/mark",
        headers=auth,
        json={"date": "2026-08-10", "state": "partial"},
    )
    assert partial.json() == {"date": "2026-08-10", "state": "partial"}
    assert _days(client)["2026-08-10"] == "partial"

    again = client.post(
        "/api/habits/quran/mark",
        headers=auth,
        json={"date": "2026-08-10", "state": "partial"},
    )
    assert again.json()["state"] == "partial"
    assert _days(client)["2026-08-10"] == "partial"

    back = client.post(
        "/api/habits/quran/mark",
        headers=auth,
        json={"date": "2026-08-10", "state": "done"},
    )
    assert back.json()["state"] == "done"
    assert _days(client)["2026-08-10"] is True


def test_none_deletes_the_key_rather_than_storing_a_value(client, auth, habit):
    client.post(
        "/api/habits/quran/mark",
        headers=auth,
        json={"date": "2026-08-10", "state": "partial"},
    )
    cleared = client.post(
        "/api/habits/quran/mark",
        headers=auth,
        json={"date": "2026-08-10", "state": "none"},
    )
    assert cleared.json() == {"date": "2026-08-10", "state": "none"}
    # Absent, not `false` and not `"none"` — every read spells "not done" as
    # "no key", and a stored third value would have to be filtered out of them.
    assert "2026-08-10" not in _days(client)

    # Clearing a day that was never marked is fine, not a 404 or a crash.
    twice = client.post(
        "/api/habits/quran/mark",
        headers=auth,
        json={"date": "2026-08-11", "state": "none"},
    )
    assert twice.status_code == 200
    assert twice.json()["state"] == "none"


def test_get_carries_partial_through_beside_true(client, auth, habit):
    client.post(
        "/api/habits/quran/mark", headers=auth, json={"date": "2026-08-09", "state": "done"}
    )
    client.post(
        "/api/habits/quran/mark",
        headers=auth,
        json={"date": "2026-08-10", "state": "partial"},
    )

    days = _days(client)
    assert days == {"2026-08-09": True, "2026-08-10": "partial"}
    # The whole point of `true` over `"done"`: an old client only truthy-checks.
    assert all(days.values())


def test_bad_state_and_bad_date_are_422(client, auth, habit):
    bad_state = client.post(
        "/api/habits/quran/mark",
        headers=auth,
        json={"date": "2026-08-10", "state": "sort-of"},
    )
    assert bad_state.status_code == 422

    # "2026-8-10" and "20260810" are the dangerous ones: strptime and
    # fromisoformat respectively would take them and write a key no other read
    # can find, because every other read builds its key with isoformat().
    for bad in ("10-08-2026", "2026-8-10", "20260810", "2026-08-10T00:00",
                "2026-02-31", "tomorrow", ""):
        res = client.post(
            "/api/habits/quran/mark", headers=auth, json={"date": bad, "state": "done"}
        )
        assert res.status_code == 422, f"{bad!r} was accepted"

    missing = client.post(
        "/api/habits/quran/mark", headers=auth, json={"date": "2026-08-10"}
    )
    assert missing.status_code == 422


def test_mark_is_admin_only_and_404s_on_an_unknown_habit(client, auth, habit):
    # A fresh client: `auth` logged in, which also set the HttpOnly bk_admin
    # cookie on the shared one, so dropping the header alone proves nothing.
    anon = client.__class__(client.app)
    res = anon.post("/api/habits/quran/mark", json={"date": "2026-08-10", "state": "done"})
    assert res.status_code == 401
    assert "2026-08-10" not in _days(client)

    unknown = client.post(
        "/api/habits/nope/mark", headers=auth, json={"date": "2026-08-10", "state": "done"}
    )
    assert unknown.status_code == 404


def test_toggle_is_still_the_old_boolean(client, auth, habit):
    """Unchanged on purpose: it is the old UI's tap, and it may clobber partial."""
    on = client.post("/api/habits/quran/toggle?target_date=2026-08-10", headers=auth)
    assert on.json() == {"date": "2026-08-10", "completed": True}
    assert _days(client)["2026-08-10"] is True

    off = client.post("/api/habits/quran/toggle?target_date=2026-08-10", headers=auth)
    assert off.json() == {"date": "2026-08-10", "completed": False}
    assert "2026-08-10" not in _days(client)

    # A partial day un-ticks to absent — accepted: the boolean UI has no third
    # answer to give, so "not done" is the honest reading of its tap.
    client.post(
        "/api/habits/quran/mark",
        headers=auth,
        json={"date": "2026-08-10", "state": "partial"},
    )
    cleared = client.post("/api/habits/quran/toggle?target_date=2026-08-10", headers=auth)
    assert cleared.json()["completed"] is False
    assert "2026-08-10" not in _days(client)

    # And a fresh tick after that is a full "done", not a resurrected partial.
    client.post("/api/habits/quran/toggle?target_date=2026-08-10", headers=auth)
    assert _days(client)["2026-08-10"] is True


def test_a_partial_day_still_counts_toward_stats_and_the_streak(client, auth, habit):
    """Deliberate: partial is nearer to done than to missed (review_score's call)."""
    from datetime import date

    today = date.today().isoformat()
    client.post(
        "/api/habits/quran/mark", headers=auth, json={"date": today, "state": "partial"}
    )

    stats = client.get("/api/habits/quran/stats").json()
    assert stats["completed"] == 1
    assert stats["current_streak"] == 1
