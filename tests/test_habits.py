"""Habit categories — "education", "health", "islam".

A free string, nullable, and blank means ungrouped: an empty box in the UI and
an omitted field have to end up as the same NULL, or the grouped list grows a
"" lane nobody asked for.
"""

from app.schemas.habit import HabitUpdate
from app.services import habits as svc


def _create(client, auth, habit_id: str, **extra):
    body = {"id": habit_id, "name": habit_id.title(), "emoji": "📖", "color": "red", **extra}
    res = client.post("/api/habits", json=body, headers=auth)
    assert res.status_code == 201, res.text
    return res.json()


# --- the normalizer (pure) ------------------------------------------------


def test_a_category_is_trimmed_and_blank_means_none():
    assert svc.normalize_category("  islam ") == "islam"
    assert svc.normalize_category("") is None
    assert svc.normalize_category("   ") is None
    assert svc.normalize_category(None) is None


# --- create ---------------------------------------------------------------


def test_a_category_round_trips_through_create_and_the_list(client, auth):
    created = _create(client, auth, "quran", category="islam")
    assert created["category"] == "islam"

    listed = client.get("/api/habits").json()
    assert [h["category"] for h in listed] == ["islam"]


def test_a_habit_created_without_a_category_is_ungrouped(client, auth):
    assert _create(client, auth, "run")["category"] is None
    assert client.get("/api/habits").json()[0]["category"] is None


def test_a_blank_category_normalizes_to_null_rather_than_an_empty_group(client, auth):
    assert _create(client, auth, "read", category="   ")["category"] is None
    assert client.get("/api/habits").json()[0]["category"] is None


def test_a_category_is_stored_trimmed(client, auth):
    assert _create(client, auth, "gym", category="  health  ")["category"] == "health"


# --- update ---------------------------------------------------------------


def test_the_category_can_be_set_on_an_existing_habit(client, auth):
    _create(client, auth, "quran")
    res = client.patch("/api/habits/quran", json={"category": "islam"}, headers=auth)
    assert res.status_code == 200, res.text
    assert res.json()["category"] == "islam"


def test_a_blank_category_clears_it_back_to_ungrouped(client, auth):
    _create(client, auth, "quran", category="islam")
    res = client.patch("/api/habits/quran", json={"category": ""}, headers=auth)
    assert res.json()["category"] is None


def test_an_omitted_category_leaves_the_existing_one_alone(client, auth):
    """"No category given" and "no category, please" are different requests."""
    _create(client, auth, "quran", category="islam")
    res = client.patch("/api/habits/quran", json={"name": "Quran reading"}, headers=auth)
    assert res.json() == {**res.json(), "name": "Quran reading", "category": "islam"}


def test_updating_a_habit_that_is_not_there_is_a_404(client, auth):
    assert client.patch("/api/habits/ghost", json={"category": "x"}, headers=auth).status_code == 404


def test_editing_a_habit_is_admin_only(client, auth):
    _create(client, auth, "quran")
    # A fresh client — the logged-in one carries the HttpOnly session cookie.
    anon = client.__class__(client.app)
    assert anon.patch("/api/habits/quran", json={"category": "islam"}).status_code == 401
    assert client.get("/api/habits").json()[0]["category"] is None


def test_the_service_updates_without_touching_the_untouched(db):
    svc.create_habit(db, "quran", "Quran", "📖", "green", category="islam")
    assert svc.update_habit(db, "quran", HabitUpdate(category="faith")) is True

    habit = svc.list_habits(db)[0]
    assert (habit.category, habit.name, habit.emoji) == ("faith", "Quran", "📖")
    assert svc.update_habit(db, "nope", HabitUpdate(category="x")) is False
