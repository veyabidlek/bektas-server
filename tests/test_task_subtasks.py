"""A checklist inside a task.

Bektas asked for a popup on a task with subtasks in it (2026-09-05) and chose
the small version: a subtask is a line with a tick, not a task. It has no
status, no due date and no tags, and finishing all of them does not finish the
parent — he ticks that himself.

⚠️⚠️ THE CLAIM THESE TESTS EXIST FOR: a subtask must never reach a number that
counts tasks. The morning brief, the weekly digest, the dashboard card and the
backlog all query `tasks`, and a checklist item turning up in tomorrow's brief
is the failure this feature could plausibly cause. Living in its own table is
what makes that impossible rather than merely unlikely, and the tests below are
what stop somebody "simplifying" it back into `tasks`.
"""


def _task(client, auth, **body):
    body.setdefault("title", "a task")
    res = client.post("/api/tasks", headers=auth, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _sub(client, auth, task_id, title="a step"):
    res = client.post(
        f"/api/tasks/{task_id}/subtasks", headers=auth, json={"title": title}
    )
    assert res.status_code == 201, res.text
    return res.json()


def _get(client, auth, task_id):
    res = client.get("/api/tasks", headers=auth)
    assert res.status_code == 200, res.text
    return next(t for t in res.json() if t["id"] == task_id)


# ------------------------------------------------------------ the checklist


def test_a_task_starts_with_no_subtasks(client, auth):
    assert _task(client, auth)["subtasks"] == []


def test_subtasks_come_back_with_the_task_in_order(client, auth):
    task = _task(client, auth)
    _sub(client, auth, task["id"], "first")
    _sub(client, auth, task["id"], "second")
    _sub(client, auth, task["id"], "third")

    # Sent with the task rather than fetched per card: the board draws a "2/5"
    # badge, and a request per card is a request per card.
    got = _get(client, auth, task["id"])
    assert [s["title"] for s in got["subtasks"]] == ["first", "second", "third"]
    assert all(s["done"] is False for s in got["subtasks"])


def test_a_subtask_can_be_ticked_renamed_and_deleted(client, auth):
    task = _task(client, auth)
    sub = _sub(client, auth, task["id"])

    ticked = client.patch(
        f"/api/tasks/subtasks/{sub['id']}", headers=auth, json={"done": True}
    )
    assert ticked.status_code == 200, ticked.text
    assert ticked.json()["done"] is True

    renamed = client.patch(
        f"/api/tasks/subtasks/{sub['id']}", headers=auth, json={"title": "renamed"}
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["title"] == "renamed"
    assert renamed.json()["done"] is True, "a rename must not untick it"

    assert client.delete(f"/api/tasks/subtasks/{sub['id']}", headers=auth).status_code == 204
    assert _get(client, auth, task["id"])["subtasks"] == []


def test_a_blank_subtask_is_refused(client, auth):
    task = _task(client, auth)
    res = client.post(
        f"/api/tasks/{task['id']}/subtasks", headers=auth, json={"title": "   "}
    )
    assert res.status_code == 422, res.text


def test_a_subtask_on_a_task_that_does_not_exist_is_a_404(client, auth):
    res = client.post("/api/tasks/nope/subtasks", headers=auth, json={"title": "x"})
    assert res.status_code == 404, res.text


def test_the_subtasks_route_is_not_swallowed_by_the_task_routes(client, auth):
    """`/tasks/subtasks/{id}` must be matched before `/tasks/{task_id}`.

    The same trap `/tasks/tags` has: registered the other way round, "subtasks"
    reads as a task id and every one of these answers 404.
    """
    task = _task(client, auth)
    sub = _sub(client, auth, task["id"])
    assert client.patch(
        f"/api/tasks/subtasks/{sub['id']}", headers=auth, json={"done": True}
    ).status_code == 200


# --------------------------------------------------- what must NOT be touched


def test_deleting_a_task_takes_its_subtasks(client, auth):
    task = _task(client, auth)
    sub = _sub(client, auth, task["id"])

    assert client.delete(f"/api/tasks/{task['id']}", headers=auth).status_code == 204
    # The row is gone with its parent, not orphaned waiting to re-attach to
    # whatever reuses the id.
    orphan = client.patch(
        f"/api/tasks/subtasks/{sub['id']}", headers=auth, json={"done": True}
    )
    assert orphan.status_code == 404, orphan.text


def test_deleting_a_subtask_leaves_the_task(client, auth):
    task = _task(client, auth, title="still here")
    sub = _sub(client, auth, task["id"])
    client.delete(f"/api/tasks/subtasks/{sub['id']}", headers=auth)
    assert _get(client, auth, task["id"])["title"] == "still here"


def test_ticking_a_subtask_never_moves_the_parent(client, auth):
    """⚠️⚠️ Finishing the checklist does NOT finish the task — his call.

    And more importantly `status`, `done` and `done_at` are written by exactly
    one function. A subtask must not become a second writer of them.
    """
    task = _task(client, auth)
    before = (task["status"], task["done"], task["done_at"])

    subs = [_sub(client, auth, task["id"], f"step {i}") for i in range(3)]
    for sub in subs:
        client.patch(f"/api/tasks/subtasks/{sub['id']}", headers=auth, json={"done": True})

    after = _get(client, auth, task["id"])
    assert (after["status"], after["done"], after["done_at"]) == before
    assert all(s["done"] for s in after["subtasks"])


def test_a_subtask_is_not_a_task_and_reaches_no_task_count(client, auth):
    """The one that matters: a checklist item must not enter the brief.

    `/api/tasks` is what the backlog reads and `/api/tasks/today` is what the
    dashboard card and the bot's morning brief read. Neither may grow because
    somebody wrote down a step.
    """
    before_list = len(client.get("/api/tasks", headers=auth).json())
    before_today = client.get("/api/tasks/today", headers=auth).json()

    task = _task(client, auth, dueAt=None)
    for i in range(5):
        _sub(client, auth, task["id"], f"step {i}")

    after_list = client.get("/api/tasks", headers=auth).json()
    after_today = client.get("/api/tasks/today", headers=auth).json()

    # Exactly one new row: the task. The five steps are not tasks.
    assert len(after_list) == before_list + 1
    assert after_today["overdue_count"] == before_today["overdue_count"]
    assert after_today["today_count"] == before_today["today_count"]
