"""The tasks assistant: what it counts, what it parses, and what it refuses.

No network anywhere in here. `parse_capture` and `summarize` are pure, which
is the point of the split — the failure modes that actually happen (a fenced
block, `urgent: "maybe"`, a made-up date shape) are the ones worth pinning,
and none of them need DeepSeek to reproduce.
"""

import pytest

from app.schemas.task import TaskOut
from app.services import task_insights, tasks_ai


def _task(**over) -> TaskOut:
    base = dict(
        id="t1",
        title="a task",
        notes="",
        due_at=None,
        due_all_day=False,
        status="todo",
        done=False,
        done_at=None,
        urgent=None,
        important=None,
        quadrant="unsorted",
        archived_at=None,
        source="web",
        created_at="2026-08-01T09:00:00+05:00",
        updated_at="2026-08-01T09:00:00+05:00",
    )
    base.update(over)
    return TaskOut(**base)


TODAY = "2026-08-20"


class TestInsights:
    def test_counts_each_column(self):
        out = task_insights.summarize(
            [
                _task(status="todo"),
                _task(status="in_progress", updated_at=TODAY),
                _task(status="done", done=True),
                _task(status="done", done=True),
            ],
            TODAY,
        )
        assert (out.todo, out.in_progress, out.done) == (1, 1, 2)

    def test_overdue_is_open_dated_and_past(self):
        out = task_insights.summarize(
            [
                _task(id="a", due_at="2026-08-19", title="late"),
                _task(id="b", due_at=TODAY),
                _task(id="c", due_at="2026-08-25"),
                _task(id="d"),
            ],
            TODAY,
        )
        assert out.overdue == 1
        assert out.overdue_titles == ["late"]
        assert out.undated == 1

    def test_a_finished_task_is_never_overdue_or_untriaged(self):
        """The bug this pins: counting done tasks would report a backlog of
        problems made entirely of work he has already finished."""
        out = task_insights.summarize(
            [_task(status="done", done=True, due_at="2026-01-01")],
            TODAY,
        )
        assert out.overdue == 0
        assert out.unsorted == 0
        assert out.undated == 0
        assert out.done == 1

    def test_stalled_is_in_progress_and_untouched(self):
        out = task_insights.summarize(
            [
                _task(id="a", status="in_progress", updated_at="2026-08-01", title="old"),
                _task(id="b", status="in_progress", updated_at="2026-08-19"),
                # Not in progress, so however old it is, it is not stalled.
                _task(id="c", status="todo", updated_at="2026-01-01"),
            ],
            TODAY,
        )
        assert out.stalled == 1
        assert out.stalled_titles == ["old"]

    def test_quadrant_counts(self):
        out = task_insights.summarize(
            [
                _task(id="a", quadrant="do_first", title="urgent thing"),
                _task(id="b", quadrant="schedule"),
                _task(id="c"),
                _task(id="d"),
            ],
            TODAY,
        )
        assert out.do_first == 1
        assert out.do_first_titles == ["urgent thing"]
        assert out.unsorted == 2

    def test_names_at_most_a_handful(self):
        many = [_task(id=str(i), due_at="2026-01-01", title=f"t{i}") for i in range(20)]
        out = task_insights.summarize(many, TODAY)
        assert out.overdue == 20
        assert len(out.overdue_titles) == task_insights.NAMED

    def test_an_empty_board_still_answers(self):
        out = task_insights.summarize([], TODAY)
        assert out.today == TODAY
        assert (out.todo, out.overdue, out.unsorted) == (0, 0, 0)

    def test_the_context_only_states_computed_facts(self):
        out = task_insights.summarize([_task(due_at="2026-08-19", title="late")], TODAY)
        context = task_insights.as_context(out)
        assert TODAY in context
        assert "Overdue: 1" in context
        assert "late" in context

    def test_a_malformed_timestamp_does_not_blow_up_the_summary(self):
        out = task_insights.summarize([_task(status="in_progress", updated_at="???")], TODAY)
        assert out.in_progress == 1
        assert out.stalled == 0


class TestParseCapture:
    def test_the_documented_shape(self):
        tasks = tasks_ai.parse_capture(
            '{"tasks": [{"title": "Renew the domain", "notes": "before it lapses",'
            ' "due_at": "2026-09-01", "urgent": true, "important": true}]}'
        )
        assert tasks == [
            {
                "title": "Renew the domain",
                "notes": "before it lapses",
                "due_at": "2026-09-01",
                "urgent": True,
                "important": True,
            }
        ]

    def test_a_fenced_block(self):
        tasks = tasks_ai.parse_capture('```json\n{"tasks": [{"title": "Call Madina"}]}\n```')
        assert tasks and tasks[0]["title"] == "Call Madina"

    def test_a_bare_list(self):
        tasks = tasks_ai.parse_capture('[{"title": "Ship the board"}]')
        assert tasks and tasks[0]["title"] == "Ship the board"

    def test_a_list_of_plain_strings(self):
        tasks = tasks_ai.parse_capture('["Book the flight", "Pack"]')
        assert [t["title"] for t in tasks] == ["Book the flight", "Pack"]

    @pytest.mark.parametrize("text", ["", "not json at all", "{}", '{"tasks": []}', "null"])
    def test_nothing_usable_is_none_not_an_exception(self, text):
        assert tasks_ai.parse_capture(text) is None

    def test_a_task_with_no_title_is_dropped(self):
        tasks = tasks_ai.parse_capture('{"tasks": [{"title": "  "}, {"title": "Real"}]}')
        assert [t["title"] for t in tasks] == ["Real"]

    def test_it_caps_how_many_it_will_accept(self):
        many = ", ".join(f'{{"title": "t{i}"}}' for i in range(30))
        tasks = tasks_ai.parse_capture(f'{{"tasks": [{many}]}}')
        assert len(tasks) == tasks_ai.MAX_TASKS

    @pytest.mark.parametrize(
        "raw,expected",
        [("true", True), ("yes", True), ("false", False), ("no", False)],
    )
    def test_a_stringly_boolean_is_understood(self, raw, expected):
        tasks = tasks_ai.parse_capture(f'{{"tasks": [{{"title": "x", "urgent": "{raw}"}}]}}')
        assert tasks[0]["urgent"] is expected

    @pytest.mark.parametrize("raw", ['"maybe"', "1", "null", '""', "{}"])
    def test_an_unclear_boolean_becomes_none_never_false(self, raw):
        """False is a real answer — it files a task under "Eliminate". A parser
        that reaches it by accident quietly mis-triages the backlog."""
        tasks = tasks_ai.parse_capture(f'{{"tasks": [{{"title": "x", "important": {raw}}}]}}')
        assert tasks[0]["important"] is None

    @pytest.mark.parametrize(
        "raw", ['"tomorrow"', '"2026-8-3"', '"next friday"', '"2026-09-01T10:00"', "12345", "null"]
    )
    def test_only_a_plain_day_survives_as_a_deadline(self, raw):
        """A wrong deadline is worse than no deadline, and every shape here is
        one no reader of this column could compare."""
        tasks = tasks_ai.parse_capture(f'{{"tasks": [{{"title": "x", "due_at": {raw}}}]}}')
        assert tasks[0]["due_at"] is None

    def test_long_text_is_truncated_rather_than_refused(self):
        tasks = tasks_ai.parse_capture(
            '{"tasks": [{"title": "%s", "notes": "%s"}]}' % ("t" * 500, "n" * 900)
        )
        assert len(tasks[0]["title"]) == tasks_ai.MAX_TITLE
        assert len(tasks[0]["notes"]) == tasks_ai.MAX_NOTES


class TestRoutes:
    def test_capture_needs_something_to_read(self, client, auth):
        res = client.post("/api/tasks/ai/capture", headers=auth, json={"note": "   "})
        assert res.status_code == 422

    def test_capture_without_a_key_is_503_that_says_why(self, client, auth, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        res = client.post("/api/tasks/ai/capture", headers=auth, json={"note": "call the bank"})
        assert res.status_code == 503
        assert "DEEPSEEK_API_KEY" in res.json()["detail"]

    def test_analysis_still_answers_with_no_model(self, client, auth, monkeypatch):
        """⚠️ 200, not 503. The counts do not need a model and are the useful
        half — only the paragraph is optional."""
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        client.post("/api/tasks", headers=auth, json={"title": "Something", "due_at": "2026-01-01"})

        res = client.get("/api/tasks/ai/analysis", headers=auth)
        assert res.status_code == 200
        body = res.json()
        assert body["summary"] is None
        assert body["insights"]["overdue"] == 1
        assert body["insights"]["unsorted"] == 1

    def test_analysis_ignores_archived_tasks(self, client, auth, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        task = client.post(
            "/api/tasks", headers=auth, json={"title": "Abandoned", "due_at": "2026-01-01"}
        ).json()
        before = client.get("/api/tasks/ai/analysis", headers=auth).json()["insights"]["overdue"]

        client.patch(f"/api/tasks/{task['id']}/archive", headers=auth)
        after = client.get("/api/tasks/ai/analysis", headers=auth).json()["insights"]["overdue"]
        assert after == before - 1

    def test_the_ai_routes_are_admin_only(self, client):
        anon = client.__class__(client.app)
        assert anon.post("/api/tasks/ai/capture", json={"note": "x"}).status_code == 401
        assert anon.get("/api/tasks/ai/analysis").status_code == 401

    def test_capture_is_not_swallowed_by_the_id_routes(self, client, auth, monkeypatch):
        """"ai" sits where a task id goes. Without the declaration order this
        would 404 as "task not found" on a page with no login to explain it."""
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        res = client.get("/api/tasks/ai/analysis", headers=auth)
        assert res.status_code == 200
