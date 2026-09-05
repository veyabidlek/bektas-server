"""Tags on tasks, and the board filter that reads them.

Bektas runs several projects at once and wanted the board to show one project
at a time (2026-09-05). A tag is a managed row — created once, given a colour,
picked from a list — rather than free text, so renaming a project is one edit
instead of a sweep over every task.

The claims worth guarding are about what a tag is NOT allowed to touch. A tag
and a task are joined through `task_tag_links`, and deleting either end must
take the links with it and nothing else: removing a project must not remove the
work, and finishing the work must not remove the project. The old failure this
is guarding against is the one `_apply_status` already documents — a second
writer of task state — so these tests also check that assigning tags leaves
`status`, `done` and `done_at` exactly where they were.
"""

import pytest


def _task(client, auth, **body):
    body.setdefault("title", "a task")
    res = client.post("/api/tasks", headers=auth, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _tag(client, auth, name="Tapsyr", color="blue"):
    res = client.post("/api/tasks/tags", headers=auth, json={"name": name, "color": color})
    assert res.status_code == 201, res.text
    return res.json()


def _get(client, auth, task_id):
    res = client.get("/api/tasks", headers=auth)
    assert res.status_code == 200, res.text
    return next(t for t in res.json() if t["id"] == task_id)


# ------------------------------------------------------------------ the tags


def test_create_list_and_rename_a_tag(client, auth):
    tag = _tag(client, auth, "Shakyrtu", "green")
    assert tag["name"] == "Shakyrtu"
    assert tag["color"] == "green"

    listed = client.get("/api/tasks/tags", headers=auth)
    assert listed.status_code == 200
    assert [t["id"] for t in listed.json()] == [tag["id"]]

    # The whole point of a managed tag: renaming the project is ONE edit, and
    # every task wearing it follows without being touched.
    renamed = client.patch(
        f"/api/tasks/tags/{tag['id']}", headers=auth, json={"name": "Shakyrtu.kz"}
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Shakyrtu.kz"
    assert renamed.json()["color"] == "green", "a rename must not reset the colour"


def test_a_tag_name_is_taken_once_whatever_the_case(client, auth):
    _tag(client, auth, "Tapsyr")
    clash = client.post("/api/tasks/tags", headers=auth, json={"name": "  tapsyr "})
    assert clash.status_code == 409, clash.text

    other = _tag(client, auth, "Bektas.app")
    rename_clash = client.patch(
        f"/api/tasks/tags/{other['id']}", headers=auth, json={"name": "TAPSYR"}
    )
    assert rename_clash.status_code == 409, rename_clash.text


def test_a_blank_tag_name_is_refused(client, auth):
    res = client.post("/api/tasks/tags", headers=auth, json={"name": "   "})
    assert res.status_code == 422, res.text


# ------------------------------------------------- putting tags on the tasks


def test_a_task_carries_several_tags_and_reports_them(client, auth):
    a = _tag(client, auth, "Tapsyr", "blue")
    b = _tag(client, auth, "Shakyrtu", "green")

    task = _task(client, auth, title="ship the import", tag_ids=[a["id"], b["id"]])
    assert {t["id"] for t in task["tags"]} == {a["id"], b["id"]}
    # The chip needs the colour, and asking for it separately would be a second
    # request per card.
    assert {t["color"] for t in task["tags"]} == {"blue", "green"}

    assert {t["id"] for t in _get(client, auth, task["id"])["tags"]} == {a["id"], b["id"]}


def test_the_same_tag_twice_lands_once(client, auth):
    a = _tag(client, auth)
    task = _task(client, auth, tag_ids=[a["id"], a["id"]])
    assert len(task["tags"]) == 1


def test_an_unknown_tag_id_is_refused_rather_than_ignored(client, auth):
    res = client.post(
        "/api/tasks", headers=auth, json={"title": "x", "tag_ids": ["no-such-tag"]}
    )
    assert res.status_code == 404, res.text


def test_omitting_tag_ids_leaves_the_tags_alone_and_an_empty_list_clears_them(client, auth):
    """The file's own `exclude_unset` convention, applied to tags.

    ⚠️ This is the difference between "I did not mention tags" and "remove every
    tag". A PUT that renames a task must not silently strip its project.
    """
    a = _tag(client, auth)
    task = _task(client, auth, tag_ids=[a["id"]])

    renamed = client.put(
        f"/api/tasks/{task['id']}", headers=auth, json={"title": "renamed"}
    )
    assert renamed.status_code == 200, renamed.text
    assert len(renamed.json()["tags"]) == 1, "an unmentioned tag list must survive"

    cleared = client.put(f"/api/tasks/{task['id']}", headers=auth, json={"tag_ids": []})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["tags"] == []


def test_setting_tags_replaces_the_whole_set(client, auth):
    a = _tag(client, auth, "Tapsyr")
    b = _tag(client, auth, "Shakyrtu")
    task = _task(client, auth, tag_ids=[a["id"]])

    res = client.put(f"/api/tasks/{task['id']}", headers=auth, json={"tag_ids": [b["id"]]})
    assert res.status_code == 200, res.text
    assert [t["id"] for t in res.json()["tags"]] == [b["id"]]


# --------------------------------------------------- what deletion must NOT do


def test_deleting_a_tag_keeps_the_tasks(client, auth):
    """Dropping a project is not abandoning its work."""
    a = _tag(client, auth)
    task = _task(client, auth, title="still mine", tag_ids=[a["id"]])

    res = client.delete(f"/api/tasks/tags/{a['id']}", headers=auth)
    assert res.status_code == 204, res.text

    survivor = _get(client, auth, task["id"])
    assert survivor["title"] == "still mine"
    assert survivor["tags"] == [], "the link goes with the tag, the task does not"


def test_deleting_a_task_keeps_the_tag(client, auth):
    a = _tag(client, auth)
    task = _task(client, auth, tag_ids=[a["id"]])

    assert client.delete(f"/api/tasks/{task['id']}", headers=auth).status_code == 204

    listed = client.get("/api/tasks/tags", headers=auth)
    assert [t["id"] for t in listed.json()] == [a["id"]]


# --------------------------------------------- tags must not move a task's state


@pytest.mark.parametrize("status", ["todo", "in_progress", "done"])
def test_tagging_never_touches_status_done_or_done_at(client, auth, status):
    """`_apply_status` is the only writer of those three. Tags are not a fourth.

    A tag write goes through the same update path as a title write, so this is
    the guard that it stayed a title-shaped write.
    """
    a = _tag(client, auth)
    task = _task(client, auth, status=status)
    before = (task["status"], task["done"], task["done_at"])

    res = client.put(f"/api/tasks/{task['id']}", headers=auth, json={"tag_ids": [a["id"]]})
    assert res.status_code == 200, res.text
    after = res.json()
    assert (after["status"], after["done"], after["done_at"]) == before
    assert after["done"] is (after["status"] == "done")


def test_an_archived_task_keeps_its_tags(client, auth):
    """Archiving hides a task; it does not un-file it."""
    a = _tag(client, auth)
    task = _task(client, auth, tag_ids=[a["id"]])

    res = client.patch(f"/api/tasks/{task['id']}/archive", headers=auth, json={})
    assert res.status_code == 200, res.text
    assert res.json()["archived_at"] is not None
    assert [t["id"] for t in res.json()["tags"]] == [a["id"]]
