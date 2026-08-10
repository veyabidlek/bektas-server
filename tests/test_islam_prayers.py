"""The prayer grid.

The claim worth defending: an unmarked cell and a skipped one are different
things, and both survive a round trip. Clearing a cell has to take the row off
the table rather than write two NULLs, or the distinction quietly dies.
"""


def _put(client, auth, date, prayer, status=None, quality=None):
    return client.put(
        f"/api/islam/prayers/{date}/{prayer}",
        headers=auth,
        json={"status": status, "quality": quality},
    )


def test_prayers_are_admin_only(client):
    anon = client.__class__(client.app)
    assert anon.get("/api/islam/prayers?from=2026-08-01&to=2026-08-02").status_code == 401
    assert anon.put(
        "/api/islam/prayers/2026-08-01/fajr", json={"status": "in_time", "quality": None}
    ).status_code == 401


def test_a_mark_comes_back_as_the_whole_day(client, auth):
    res = _put(client, auth, "2026-08-10", "fajr", "in_time", "focus")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["date"] == "2026-08-10"
    assert body["entries"] == {"fajr": {"status": "in_time", "quality": "focus"}}

    # A second prayer joins the same day rather than replacing it.
    body = _put(client, auth, "2026-08-10", "isha", "late", "lazy").json()
    assert set(body["entries"]) == {"fajr", "isha"}
    assert body["entries"]["isha"] == {"status": "late", "quality": "lazy"}


def test_marking_the_same_cell_twice_edits_it(client, auth):
    _put(client, auth, "2026-08-10", "asr", "skipped", None)
    body = _put(client, auth, "2026-08-10", "asr", "qaza_restored", "focus").json()
    assert body["entries"] == {"asr": {"status": "qaza_restored", "quality": "focus"}}


def test_clearing_both_fields_removes_the_cell(client, auth):
    """Not "skipped" — *unmarked*. The row has to go away."""
    _put(client, auth, "2026-08-10", "dhuhr", "in_time", "focus")
    body = _put(client, auth, "2026-08-10", "dhuhr", None, None).json()
    assert body["entries"] == {}

    days = client.get(
        "/api/islam/prayers?from=2026-08-10&to=2026-08-10", headers=auth
    ).json()["days"]
    assert days[0]["entries"] == {}


def test_a_status_without_a_quality_is_fine(client, auth):
    body = _put(client, auth, "2026-08-10", "tahajjud", "in_time").json()
    assert body["entries"]["tahajjud"] == {"status": "in_time", "quality": None}

    # And a quality without a status — the cell still exists.
    body = _put(client, auth, "2026-08-10", "awwabin", None, "lazy").json()
    assert body["entries"]["awwabin"] == {"status": None, "quality": "lazy"}


def test_all_seven_prayers_are_accepted(client, auth):
    for prayer in ("fajr", "dhuhr", "asr", "maghrib", "isha", "awwabin", "tahajjud"):
        assert _put(client, auth, "2026-08-10", prayer, "in_time").status_code == 200

    body = client.get(
        "/api/islam/prayers?from=2026-08-10&to=2026-08-10", headers=auth
    ).json()["days"][0]
    assert len(body["entries"]) == 7


def test_an_unknown_prayer_status_or_quality_is_refused(client, auth):
    assert _put(client, auth, "2026-08-10", "witr", "in_time").status_code == 422
    assert _put(client, auth, "2026-08-10", "fajr", "prayed").status_code == 422
    assert _put(client, auth, "2026-08-10", "fajr", "in_time", "distracted").status_code == 422
    assert _put(client, auth, "not-a-date", "fajr", "in_time").status_code == 422


# --- the range read -------------------------------------------------------


def test_every_day_in_the_range_is_present_even_untouched_ones(client, auth):
    _put(client, auth, "2026-08-03", "fajr", "in_time", "focus")

    days = client.get(
        "/api/islam/prayers?from=2026-08-01&to=2026-08-05", headers=auth
    ).json()["days"]
    assert [d["date"] for d in days] == [
        "2026-08-01",
        "2026-08-02",
        "2026-08-03",
        "2026-08-04",
        "2026-08-05",
    ]
    assert days[0]["entries"] == {}
    assert days[2]["entries"] == {"fajr": {"status": "in_time", "quality": "focus"}}


def test_the_range_is_inclusive_at_both_ends(client, auth):
    days = client.get(
        "/api/islam/prayers?from=2026-08-10&to=2026-08-10", headers=auth
    ).json()["days"]
    assert [d["date"] for d in days] == ["2026-08-10"]


def test_the_range_spans_a_month_boundary(client, auth):
    days = client.get(
        "/api/islam/prayers?from=2026-07-30&to=2026-08-02", headers=auth
    ).json()["days"]
    assert [d["date"] for d in days] == [
        "2026-07-30",
        "2026-07-31",
        "2026-08-01",
        "2026-08-02",
    ]


def test_marks_outside_the_range_stay_outside_it(client, auth):
    _put(client, auth, "2026-07-31", "fajr", "in_time")
    _put(client, auth, "2026-08-02", "fajr", "in_time")

    days = client.get(
        "/api/islam/prayers?from=2026-08-01&to=2026-08-01", headers=auth
    ).json()["days"]
    assert days == [{"date": "2026-08-01", "entries": {}}]


def test_an_over_long_or_backwards_range_is_refused(client, auth):
    """A typo'd `from` must not ask the server to walk the epoch a day at a time."""
    assert client.get(
        "/api/islam/prayers?from=1970-01-01&to=2026-08-10", headers=auth
    ).status_code == 422
    assert client.get(
        "/api/islam/prayers?from=2026-08-10&to=2026-08-01", headers=auth
    ).status_code == 422
    assert client.get(
        "/api/islam/prayers?from=nope&to=2026-08-01", headers=auth
    ).status_code == 422

    # Exactly 366 days is still allowed — the cap, not one short of it.
    assert client.get(
        "/api/islam/prayers?from=2026-01-01&to=2026-12-31", headers=auth
    ).status_code == 200
