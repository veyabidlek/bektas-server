"""Tasks: CRUD, the calendar's range query, the dashboard summary, and auth."""

from app.services import tasks as svc


def test_task_crud_round_trip(client, auth):
    created = client.post(
        "/api/tasks",
        headers=auth,
        json={"title": "  Renew the domain  ", "notes": "before it lapses"},
    )
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["title"] == "Renew the domain"  # trimmed
    assert task["done"] is False
    assert task["due_at"] is None
    assert task["source"] == "web"

    updated = client.put(
        f"/api/tasks/{task['id']}",
        headers=auth,
        json={"title": "Renew bektas.app", "due_at": "2026-08-20"},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Renew bektas.app"
    assert updated.json()["notes"] == "before it lapses"  # untouched field stays

    assert client.delete(f"/api/tasks/{task['id']}", headers=auth).status_code == 204
    assert client.get("/api/tasks", headers=auth).json() == []


def test_due_dates_keep_the_calendar_s_two_shapes(client, auth):
    """A plain day stays a day; a naive time is Almaty local."""
    day_only = client.post(
        "/api/tasks", headers=auth, json={"title": "day", "due_at": "2026-08-20"}
    ).json()
    assert day_only["due_at"] == "2026-08-20"
    assert day_only["due_all_day"] is True

    timed = client.post(
        "/api/tasks", headers=auth, json={"title": "timed", "due_at": "2026-08-20T14:30:00"}
    ).json()
    assert timed["due_at"] == "2026-08-20T14:30:00+05:00"
    assert timed["due_all_day"] is False


def test_toggling_done_sets_and_clears_the_timestamp(client, auth):
    task = client.post("/api/tasks", headers=auth, json={"title": "Ship it"}).json()

    ticked = client.patch(f"/api/tasks/{task['id']}/done", headers=auth).json()
    assert ticked["done"] is True
    assert ticked["done_at"] is not None

    unticked = client.patch(f"/api/tasks/{task['id']}/done", headers=auth).json()
    assert unticked["done"] is False
    # Cleared, so "recently finished" ordering never shows a stale time.
    assert unticked["done_at"] is None

    # An explicit value wins over toggling.
    forced = client.patch(
        f"/api/tasks/{task['id']}/done", headers=auth, json={"done": True}
    ).json()
    assert forced["done"] is True


def test_range_query_is_what_the_calendar_asks_for(client, auth):
    for title, due in [
        ("inside", "2026-08-12"),
        ("edge-start", "2026-08-10"),
        ("after", "2026-08-17"),
        ("undated", None),
    ]:
        client.post("/api/tasks", headers=auth, json={"title": title, "due_at": due})

    week = client.get(
        "/api/tasks", headers=auth, params={"start": "2026-08-10", "end": "2026-08-17"}
    ).json()

    # Range is half-open, and undated tasks have no place on a calendar.
    assert sorted(t["title"] for t in week) == ["edge-start", "inside"]


def test_range_includes_timed_tasks_on_the_end_day(client, auth):
    """A task at 14:00 on the 16th must not fall out of a range ending the 17th."""
    client.post(
        "/api/tasks", headers=auth, json={"title": "timed", "due_at": "2026-08-16T14:00:00"}
    )
    week = client.get(
        "/api/tasks", headers=auth, params={"start": "2026-08-10", "end": "2026-08-17"}
    ).json()
    assert [t["title"] for t in week] == ["timed"]


def test_list_can_hide_finished_tasks(client, auth):
    open_task = client.post("/api/tasks", headers=auth, json={"title": "open"}).json()
    done_task = client.post("/api/tasks", headers=auth, json={"title": "done"}).json()
    client.patch(f"/api/tasks/{done_task['id']}/done", headers=auth)

    everything = client.get("/api/tasks", headers=auth).json()
    assert len(everything) == 2

    open_only = client.get(
        "/api/tasks", headers=auth, params={"include_done": "false"}
    ).json()
    assert [t["id"] for t in open_only] == [open_task["id"]]


def test_today_summary_counts_overdue_and_today(client, auth):
    day = svc.today()
    yesterday = client.post(
        "/api/tasks", headers=auth, json={"title": "late", "due_at": "2020-01-01"}
    ).json()
    client.post("/api/tasks", headers=auth, json={"title": "due today", "due_at": day})
    client.post("/api/tasks", headers=auth, json={"title": "someday"})
    client.post("/api/tasks", headers=auth, json={"title": "far", "due_at": "2099-01-01"})

    summary = client.get("/api/tasks/today", headers=auth).json()
    assert summary["today"] == day
    assert summary["overdue_count"] == 1
    assert summary["today_count"] == 1
    # Late things surface first, and undated/far-future tasks are not the card's job.
    assert [t["title"] for t in summary["tasks"]] == ["late", "due today"]

    # Ticking the late one takes it out of the count.
    client.patch(f"/api/tasks/{yesterday['id']}/done", headers=auth)
    assert client.get("/api/tasks/today", headers=auth).json()["overdue_count"] == 0


def test_source_is_recorded_for_later_phases(client, auth):
    """Forward-compatible: the bot and inbox will post their own source."""
    task = client.post(
        "/api/tasks", headers=auth, json={"title": "from the bot", "source": "telegram"}
    ).json()
    assert task["source"] == "telegram"


def test_rejects_an_empty_title_and_a_bad_due_date(client, auth):
    assert client.post("/api/tasks", headers=auth, json={"title": "   "}).status_code == 422
    assert (
        client.post(
            "/api/tasks", headers=auth, json={"title": "x", "due_at": "not-a-date"}
        ).status_code
        == 422
    )


def test_tasks_are_admin_only(client):
    anon = client.__class__(client.app)
    assert anon.get("/api/tasks").status_code == 401
    assert anon.get("/api/tasks/today").status_code == 401
    assert anon.post("/api/tasks", json={"title": "x"}).status_code == 401
    assert anon.put("/api/tasks/abc", json={"title": "x"}).status_code == 401
    assert anon.patch("/api/tasks/abc/done").status_code == 401
    assert anon.delete("/api/tasks/abc").status_code == 401
