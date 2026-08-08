"""Calendar CRUD happy path + the guarantees around it."""


def test_event_crud_round_trip(client, auth):
    created = client.post(
        "/api/calendar/events",
        headers=auth,
        json={
            "title": "Dentist",
            "starts_at": "2026-08-20T14:30:00",
            "notes": "bring the x-ray",
            "reminder_minutes": 30,
        },
    )
    assert created.status_code == 201, created.text
    event = created.json()
    event_id = event["id"]

    # A naive datetime is Bektas's local time, so it comes back with +05:00.
    assert event["starts_at"] == "2026-08-20T14:30:00+05:00"
    assert event["reminder_minutes"] == 30
    # Unconfigured Google means no mirror, and that is not an error.
    assert event["google_event_id"] is None

    listed = client.get("/api/calendar/events", headers=auth).json()
    assert [e["id"] for e in listed] == [event_id]

    updated = client.put(
        f"/api/calendar/events/{event_id}",
        headers=auth,
        json={"title": "Dentist (moved)", "starts_at": "2026-08-21T09:00:00"},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Dentist (moved)"
    assert updated.json()["starts_at"] == "2026-08-21T09:00:00+05:00"
    # An untouched field stays put.
    assert updated.json()["notes"] == "bring the x-ray"

    assert client.delete(f"/api/calendar/events/{event_id}", headers=auth).status_code == 204
    assert client.get("/api/calendar/events", headers=auth).json() == []


def test_events_are_returned_in_chronological_order(client, auth):
    for day in ("2026-09-03", "2026-09-01", "2026-09-02"):
        client.post(
            "/api/calendar/events",
            headers=auth,
            json={"title": day, "starts_at": f"{day}T10:00:00"},
        )
    listed = client.get("/api/calendar/events", headers=auth).json()
    assert [e["title"] for e in listed] == ["2026-09-01", "2026-09-02", "2026-09-03"]


def test_month_range_filter(client, auth):
    for month in ("2026-08", "2026-09"):
        client.post(
            "/api/calendar/events",
            headers=auth,
            json={"title": month, "starts_at": f"{month}-15T10:00:00"},
        )
    august = client.get(
        "/api/calendar/events",
        headers=auth,
        params={"start": "2026-08-01", "end": "2026-09-01"},
    ).json()
    assert [e["title"] for e in august] == ["2026-08"]


def test_all_day_event_keeps_a_plain_date(client, auth):
    res = client.post(
        "/api/calendar/events",
        headers=auth,
        json={"title": "Birthday", "starts_at": "2026-08-25", "all_day": True},
    )
    assert res.status_code == 201
    assert res.json()["starts_at"] == "2026-08-25"


def test_rejects_a_missing_title_and_a_bad_date(client, auth):
    assert client.post(
        "/api/calendar/events", headers=auth, json={"title": "  ", "starts_at": "2026-08-20T10:00"}
    ).status_code == 422
    assert client.post(
        "/api/calendar/events", headers=auth, json={"title": "x", "starts_at": "not-a-date"}
    ).status_code == 422


def test_calendar_is_admin_only(client):
    assert client.get("/api/calendar/events").status_code == 401
    assert client.post(
        "/api/calendar/events", json={"title": "x", "starts_at": "2026-08-20T10:00:00"}
    ).status_code == 401


def test_google_sync_degrades_gracefully_when_unconfigured(client, auth):
    status = client.get("/api/calendar/google/status", headers=auth)
    assert status.status_code == 200
    body = status.json()
    assert body["configured"] is False
    assert body["connected"] is False
    assert body["redirect_uri"].endswith("/api/calendar/google/callback")

    # Asking for an auth URL says "not configured" rather than crashing.
    assert client.post("/api/calendar/google/auth-url", headers=auth).status_code == 409
