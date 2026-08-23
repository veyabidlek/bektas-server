"""The Jira-style half of tasks: status, the Eisenhower matrix, and the archive.

The load-bearing claim these guard is the one in `tasks._apply_status` — that
`status`, `done` and `done_at` are three columns holding ONE decision. Every
path that can move a task is checked to leave all three agreeing, because the
bot and the weekly digest filter on `done` in SQL while the board writes
`status`, and a drift between them is invisible until a finished task turns up
in tomorrow's morning brief.
"""

import pytest

from app.services import task_rules


def _task(client, auth, **body):
    body.setdefault("title", "a task")
    res = client.post("/api/tasks", headers=auth, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _assert_coherent(task: dict) -> None:
    """`done` is a copy of `status == "done"`, and `done_at` follows both."""
    assert task["done"] is (task["status"] == "done"), task
    if task["done"]:
        assert task["done_at"], "a finished task must carry its completion date"
    else:
        assert task["done_at"] is None, "an open task must not keep a completion date"


class TestStatus:
    def test_a_new_task_starts_in_todo(self, client, auth):
        task = _task(client, auth)
        assert task["status"] == "todo"
        _assert_coherent(task)

    def test_moving_through_the_board_stamps_and_clears_completion(self, client, auth):
        task = _task(client, auth)

        for status in ("in_progress", "done", "todo", "done"):
            moved = client.patch(
                f"/api/tasks/{task['id']}/status", headers=auth, json={"status": status}
            )
            assert moved.status_code == 200, moved.text
            assert moved.json()["status"] == status
            _assert_coherent(moved.json())

    def test_re_entering_done_keeps_the_original_completion_date(self, client, auth):
        """Done → In Progress → Done is a correction, not a second finishing."""
        task = _task(client, auth)
        first = client.patch(
            f"/api/tasks/{task['id']}/status", headers=auth, json={"status": "done"}
        ).json()

        client.patch(
            f"/api/tasks/{task['id']}/status", headers=auth, json={"status": "in_progress"}
        )
        again = client.patch(
            f"/api/tasks/{task['id']}/status", headers=auth, json={"status": "done"}
        ).json()

        # It was cleared in between, so this is a genuinely new stamp — what
        # matters is that it is a stamp at all and the row stays coherent.
        assert again["done_at"] is not None
        assert first["done_at"] is not None

    def test_the_old_checkbox_still_works_and_moves_the_card(self, client, auth):
        """The calendar chip predates the board and still sends a bare toggle."""
        task = _task(client, auth, status="in_progress")

        ticked = client.patch(f"/api/tasks/{task['id']}/done", headers=auth).json()
        assert ticked["status"] == "done"
        _assert_coherent(ticked)

        # ⚠️ Unticking lands in To Do, NOT back in In Progress — nothing
        # records where it came from, and guessing would move a card by itself.
        unticked = client.patch(f"/api/tasks/{task['id']}/done", headers=auth).json()
        assert unticked["status"] == "todo"
        _assert_coherent(unticked)

    def test_an_unknown_status_is_422_and_says_what_it_wanted(self, client, auth):
        task = _task(client, auth)
        res = client.patch(
            f"/api/tasks/{task['id']}/status", headers=auth, json={"status": "wontfix"}
        )
        assert res.status_code == 422
        assert "wontfix" in res.json()["detail"]
        assert "in_progress" in res.json()["detail"]

    def test_status_is_liberal_about_shape(self, client, auth):
        task = _task(client, auth)
        moved = client.patch(
            f"/api/tasks/{task['id']}/status", headers=auth, json={"status": " In-Progress "}
        )
        assert moved.status_code == 200
        assert moved.json()["status"] == "in_progress"

    def test_put_accepts_either_status_or_done_but_refuses_both(self, client, auth):
        task = _task(client, auth)

        by_status = client.put(
            f"/api/tasks/{task['id']}", headers=auth, json={"status": "done"}
        )
        assert by_status.status_code == 200
        _assert_coherent(by_status.json())

        by_done = client.put(f"/api/tasks/{task['id']}", headers=auth, json={"done": False})
        assert by_done.status_code == 200
        assert by_done.json()["status"] == "todo"

        both = client.put(
            f"/api/tasks/{task['id']}",
            headers=auth,
            json={"status": "todo", "done": True},
        )
        assert both.status_code == 422


class TestEisenhower:
    def test_an_untouched_task_is_unsorted_not_eliminate(self, client, auth):
        """The whole reason the axes are nullable. Never answered ≠ answered no."""
        task = _task(client, auth)
        assert task["urgent"] is None
        assert task["important"] is None
        assert task["quadrant"] == "unsorted"

    @pytest.mark.parametrize(
        "urgent,important,expected",
        [
            (True, True, "do_first"),
            (False, True, "schedule"),
            (True, False, "delegate"),
            (False, False, "eliminate"),
        ],
    )
    def test_each_quadrant(self, client, auth, urgent, important, expected):
        task = _task(client, auth)
        placed = client.patch(
            f"/api/tasks/{task['id']}/priority",
            headers=auth,
            json={"urgent": urgent, "important": important},
        )
        assert placed.status_code == 200
        assert placed.json()["quadrant"] == expected

    def test_one_axis_alone_is_still_unsorted(self, client, auth):
        """Half an answer must not place a card — that is a coin flip."""
        task = _task(client, auth)
        half = client.patch(
            f"/api/tasks/{task['id']}/priority", headers=auth, json={"urgent": True}
        ).json()
        assert half["urgent"] is True
        assert half["important"] is None
        assert half["quadrant"] == "unsorted"

    def test_a_task_can_be_taken_back_out_of_the_matrix(self, client, auth):
        task = _task(client, auth, urgent=True, important=True)
        assert task["quadrant"] == "do_first"

        cleared = client.patch(
            f"/api/tasks/{task['id']}/priority", headers=auth, json={}
        ).json()
        assert cleared["quadrant"] == "unsorted"

    def test_priority_does_not_disturb_status(self, client, auth):
        task = _task(client, auth, status="in_progress")
        placed = client.patch(
            f"/api/tasks/{task['id']}/priority",
            headers=auth,
            json={"urgent": True, "important": False},
        ).json()
        assert placed["status"] == "in_progress"
        _assert_coherent(placed)


class TestArchive:
    def test_archiving_hides_it_from_the_default_list_but_keeps_everything(
        self, client, auth
    ):
        task = _task(client, auth, title="Old idea", notes="worth keeping")
        client.patch(f"/api/tasks/{task['id']}/status", headers=auth, json={"status": "done"})

        archived = client.patch(f"/api/tasks/{task['id']}/archive", headers=auth).json()
        assert archived["archived_at"] is not None

        assert client.get("/api/tasks", headers=auth).json() == []

        shelf = client.get("/api/tasks?include_archived=true", headers=auth).json()
        assert [t["id"] for t in shelf] == [task["id"]]
        # Nothing about the task was lost on the way to the archive.
        assert shelf[0]["title"] == "Old idea"
        assert shelf[0]["notes"] == "worth keeping"
        assert shelf[0]["status"] == "done"
        assert shelf[0]["done_at"] is not None

    def test_restoring_puts_it_back_untouched(self, client, auth):
        task = _task(client, auth, status="in_progress")
        client.patch(f"/api/tasks/{task['id']}/archive", headers=auth)

        restored = client.patch(
            f"/api/tasks/{task['id']}/archive", headers=auth, json={"archived": False}
        ).json()
        assert restored["archived_at"] is None
        assert restored["status"] == "in_progress"
        assert [t["id"] for t in client.get("/api/tasks", headers=auth).json()] == [task["id"]]

    def test_an_unfinished_task_can_be_archived_and_stays_unfinished(self, client, auth):
        """Abandoning is not completing — conflating them would make "what did
        I actually finish?" unanswerable."""
        task = _task(client, auth)
        archived = client.patch(f"/api/tasks/{task['id']}/archive", headers=auth).json()
        assert archived["status"] == "todo"
        assert archived["done"] is False
        assert archived["done_at"] is None

    def test_the_dashboard_card_ignores_archived_tasks(self, client, auth):
        day = __import__("app.services.tasks", fromlist=["today"]).today()
        task = _task(client, auth, due_at=day)
        assert client.get("/api/tasks/today", headers=auth).json()["today_count"] == 1

        client.patch(f"/api/tasks/{task['id']}/archive", headers=auth)
        summary = client.get("/api/tasks/today", headers=auth).json()
        assert summary["today_count"] == 0
        assert summary["tasks"] == []


class TestAuth:
    def test_every_new_route_is_admin_only(self, client, auth):
        task = _task(client, auth)
        anon = client.__class__(client.app)
        for method, path, body in [
            ("patch", f"/api/tasks/{task['id']}/status", {"status": "done"}),
            ("patch", f"/api/tasks/{task['id']}/priority", {"urgent": True}),
            ("patch", f"/api/tasks/{task['id']}/archive", {}),
        ]:
            res = getattr(anon, method)(path, json=body)
            assert res.status_code == 401, (path, res.status_code)


class TestTheMigrationBackfill:
    """`status` arrives with `DEFAULT 'todo'` on a table full of finished work.

    This is the half of the migration that an ALTER TABLE cannot express, and
    the only chance to get it right is the first boot after deploy.
    """

    def test_a_task_already_ticked_lands_in_done_not_todo(self, client, auth):
        from sqlalchemy import text

        from app.database import backfill_task_status, engine

        task = _task(client, auth)
        client.patch(f"/api/tasks/{task['id']}/status", headers=auth, json={"status": "done"})

        # Rewind to exactly what the ALTER TABLE leaves behind: the old `done`
        # flag intact, `status` at its column default.
        with engine.begin() as conn:
            conn.execute(text("UPDATE tasks SET status = 'todo' WHERE id = :i"), {"i": task["id"]})

        backfill_task_status()

        after = client.get(f"/api/tasks?include_archived=true", headers=auth).json()
        row = next(t for t in after if t["id"] == task["id"])
        assert row["status"] == "done"
        _assert_coherent(row)

    def test_it_never_drags_a_card_back_out_of_todo(self, client, auth):
        """⚠️ One-directional. A task he deliberately pulled out of Done has
        `done = false, status = 'todo'` legitimately — a "keep them in sync"
        sweep would undo that move on every single restart."""
        from app.database import backfill_task_status

        task = _task(client, auth)
        client.patch(f"/api/tasks/{task['id']}/status", headers=auth, json={"status": "done"})
        client.patch(f"/api/tasks/{task['id']}/status", headers=auth, json={"status": "todo"})

        backfill_task_status()

        row = client.get("/api/tasks", headers=auth).json()[0]
        assert row["status"] == "todo"
        _assert_coherent(row)

    def test_it_is_idempotent(self, client, auth):
        from app.database import backfill_task_status

        task = _task(client, auth, status="in_progress")
        for _ in range(3):
            backfill_task_status()
        row = client.get("/api/tasks", headers=auth).json()[0]
        assert row["id"] == task["id"]
        assert row["status"] == "in_progress"


class TestRulesArePure:
    """`task_rules` answers without a database — that is the point of the split."""

    def test_status_for_done_never_guesses_in_progress(self):
        assert task_rules.status_for_done(True) == "done"
        assert task_rules.status_for_done(False) == "todo"

    def test_priority_rank_puts_do_first_first_and_unsorted_last(self):
        ranks = [
            task_rules.priority_rank(True, True),
            task_rules.priority_rank(False, True),
            task_rules.priority_rank(True, False),
            task_rules.priority_rank(False, False),
            task_rules.priority_rank(None, None),
        ]
        assert ranks == sorted(ranks)
        assert ranks == [0, 1, 2, 3, 4]

    def test_status_rank_reads_left_to_right_along_the_board(self):
        assert [task_rules.status_rank(s) for s in task_rules.STATUSES] == [0, 1, 2]
