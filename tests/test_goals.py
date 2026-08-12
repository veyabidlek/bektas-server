"""Goals: the tree comes back shaped, deleting prunes, and the model only drafts.

The invariants this suite exists to defend:

- progress is DERIVED, so the counts a page shows and the counts the assistant
  reads are the same arithmetic on the same rows;
- deleting a node takes its subtree with it, because an orphan would be drawn
  as a second root rather than reported as broken;
- a move that would make a node its own ancestor is refused;
- the AI endpoints degrade to a 503 that says why, and never write.
"""

import pytest

from app.services import goals_ai, goals_tree


@pytest.fixture()
def goal(client, auth):
    res = client.post("/api/goals", headers=auth, json={"title": "Backend engineering"})
    assert res.status_code == 201, res.text
    return res.json()


def _node(client, auth, goal_id, title, parent_id=None):
    res = client.post(
        f"/api/goals/{goal_id}/nodes",
        headers=auth,
        json={"title": title, "parent_id": parent_id},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _task(client, auth, node_id, title, due_at=None):
    res = client.post(
        f"/api/goals/nodes/{node_id}/tasks",
        headers=auth,
        json={"title": title, "due_at": due_at},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_goals_are_admin_only(client):
    # No `auth` fixture here on purpose: logging in sets the HttpOnly bk_admin
    # cookie, and TestClient keeps cookies for the rest of the session — a
    # bare request after one would still be authorized and prove nothing.
    assert client.get("/api/goals").status_code == 401
    assert client.post("/api/goals", json={"title": "x"}).status_code == 401
    assert client.post("/api/goals/ai/draft", json={"goal": "x"}).status_code == 401


def test_tree_comes_back_nested_and_counted(client, auth, goal):
    db = _node(client, auth, goal["id"], "Databases")
    idx = _node(client, auth, goal["id"], "Indexes", parent_id=db["id"])
    _task(client, auth, idx["id"], "Read the index chapter")
    done = _task(client, auth, idx["id"], "Explain a query plan")
    client.post(f"/api/goals/tasks/{done['id']}/toggle", headers=auth)

    detail = client.get(f"/api/goals/{goal['id']}", headers=auth).json()
    assert [n["title"] for n in detail["nodes"]] == ["Databases"]
    child = detail["nodes"][0]["children"][0]
    assert child["title"] == "Indexes"
    assert (child["done_count"], child["task_count"]) == (1, 2)
    # The goal's own counts are the whole tree, not just the roots.
    assert (detail["done_count"], detail["task_count"]) == (1, 2)


def test_deleting_a_node_prunes_its_subtree(client, auth, goal):
    parent = _node(client, auth, goal["id"], "Databases")
    child = _node(client, auth, goal["id"], "Indexes", parent_id=parent["id"])
    _task(client, auth, child["id"], "Read the index chapter")

    assert client.delete(f"/api/goals/nodes/{parent['id']}", headers=auth).status_code == 204
    detail = client.get(f"/api/goals/{goal['id']}", headers=auth).json()
    assert detail["nodes"] == []
    # The grandchild's task went with it — otherwise the goal would still be
    # counting work that has no box to live in.
    assert detail["task_count"] == 0


def test_a_node_cannot_become_its_own_ancestor(client, auth, goal):
    parent = _node(client, auth, goal["id"], "Databases")
    child = _node(client, auth, goal["id"], "Indexes", parent_id=parent["id"])
    res = client.patch(
        f"/api/goals/nodes/{parent['id']}", headers=auth, json={"parent_id": child["id"]}
    )
    assert res.status_code == 404


def test_toggle_stamps_and_clears_done_at(client, auth, goal):
    node = _node(client, auth, goal["id"], "Databases")
    task = _task(client, auth, node["id"], "Read the index chapter")
    assert task["done_at"] is None

    on = client.post(f"/api/goals/tasks/{task['id']}/toggle", headers=auth).json()
    assert on["done"] is True and on["done_at"]
    off = client.post(f"/api/goals/tasks/{task['id']}/toggle", headers=auth).json()
    # Cleared, not left behind: a stale stamp reads as finished to anything
    # that trusts it.
    assert off["done"] is False and off["done_at"] is None


def test_next_due_skips_finished_work(client, auth, goal):
    node = _node(client, auth, goal["id"], "Databases")
    early = _task(client, auth, node["id"], "Earlier", due_at="2026-08-20")
    _task(client, auth, node["id"], "Later", due_at="2026-09-01")

    listed = client.get("/api/goals", headers=auth).json()[0]
    assert listed["next_due_at"] == "2026-08-20"

    client.post(f"/api/goals/tasks/{early['id']}/toggle", headers=auth)
    listed = client.get("/api/goals", headers=auth).json()[0]
    # A done task's date is history; surfacing it would make a goal that is on
    # track look overdue.
    assert listed["next_due_at"] == "2026-09-01"


def test_a_day_stays_a_day_and_a_time_gains_the_offset(client, auth, goal):
    node = _node(client, auth, goal["id"], "Databases")
    day = _task(client, auth, node["id"], "Day", due_at="2026-08-20")
    moment = _task(client, auth, node["id"], "Moment", due_at="2026-08-20T14:30")
    assert day["due_at"] == "2026-08-20" and day["due_all_day"] is True
    assert moment["due_at"].startswith("2026-08-20T14:30") and moment["due_all_day"] is False


def test_ai_draft_says_why_when_there_is_no_model(client, auth, monkeypatch):
    monkeypatch.setattr(goals_ai.llm, "chat", lambda *a, **k: None)
    res = client.post("/api/goals/ai/draft", headers=auth, json={"goal": "Learn Rust"})
    assert res.status_code == 503
    assert "DEEPSEEK_API_KEY" in res.json()["detail"]


def test_ai_draft_returns_a_proposal_without_writing(client, auth, goal, monkeypatch):
    monkeypatch.setattr(
        goals_ai.llm,
        "chat",
        lambda *a, **k: '{"nodes":[{"title":"Ownership","children":[{"title":"Borrowing"}]}]}',
    )
    res = client.post("/api/goals/ai/draft", headers=auth, json={"goal": "Learn Rust"})
    assert res.status_code == 200
    assert res.json()["nodes"][0]["children"][0]["title"] == "Borrowing"
    # Nothing was saved: a model that can restructure a plan on its own is one
    # bad completion away from destroying it.
    assert client.get(f"/api/goals/{goal['id']}", headers=auth).json()["nodes"] == []


# ---- pure helpers, no database -------------------------------------------


def test_nest_orders_and_keeps_orphans_visible():
    nodes = [
        {"id": "b", "parent_id": None, "title": "B", "position": 20},
        {"id": "a", "parent_id": None, "title": "A", "position": 10},
        {"id": "a1", "parent_id": "a", "title": "A1", "position": 10},
        {"id": "lost", "parent_id": "gone", "title": "Lost", "position": 0},
    ]
    roots = goals_tree.nest(nodes)
    assert [r["title"] for r in roots] == ["Lost", "A", "B"]
    assert [c["title"] for c in roots[1]["children"]] == ["A1"]


def test_next_position_leaves_a_gap_to_insert_into():
    assert goals_tree.next_position([]) == 0
    assert goals_tree.next_position([{"position": 0}]) == 10
    assert goals_tree.next_position([{"position": 0}, {"position": 10}]) == 20


@pytest.mark.parametrize(
    "text",
    [
        "not json at all",
        "{}",
        '{"nodes": []}',
        '{"nodes": [{"description": "no title"}]}',
    ],
)
def test_parse_draft_rejects_what_it_cannot_use(text):
    assert goals_ai.parse_draft(text) is None


def test_parse_draft_survives_a_code_fence_and_a_bare_list():
    fenced = goals_ai.parse_draft('```json\n{"nodes":[{"title":"A"}]}\n```')
    assert fenced and fenced[0]["title"] == "A"
    bare = goals_ai.parse_draft('[{"title":"A"}]')
    assert bare and bare[0]["title"] == "A"


def test_parse_draft_stops_at_the_depth_limit():
    deep = {"title": "1", "children": [{"title": "2", "children": [{"title": "3", "children": [{"title": "4"}]}]}]}
    parsed = goals_ai.parse_draft(f'{{"nodes": [{__import__("json").dumps(deep)}]}}')
    assert parsed
    level3 = parsed[0]["children"][0]["children"][0]
    assert level3["title"] == "3" and level3["children"] == []


def test_parse_tasks_accepts_plain_strings():
    tasks = goals_ai.parse_tasks('{"tasks": ["Read the chapter", {"title": "Explain it"}]}')
    assert [t["title"] for t in tasks] == ["Read the chapter", "Explain it"]


# ---- the assistant learns about goals -------------------------------------


def test_goal_line_carries_the_numbers_behind_the_claim():
    from app.services import assistant_format as fmt

    line = fmt.goal_line("Backend", 3, 5, "2026-08-20", today="2026-08-13")
    # Percent alone would hide whether 60% is 3-of-5 or 300-of-500.
    assert "60%" in line and "3/5" in line and "next due 2026-08-20" in line

    overdue = fmt.goal_line("Backend", 1, 4, "2026-08-01", today="2026-08-13")
    assert "OVERDUE" in overdue

    # An empty roadmap is a plan not written, not a plan abandoned.
    assert "no tasks yet" in fmt.goal_line("New", 0, 0, None, today="2026-08-13")


def test_assistant_context_includes_active_goals(client, auth, db, goal):
    from app.services import assistant as svc

    node = _node(client, auth, goal["id"], "Databases")
    _task(client, auth, node["id"], "Read the index chapter", due_at="2026-08-20")

    context = svc.build_context(db)
    assert "ACTIVE GOALS" in context
    assert "Backend engineering" in context
