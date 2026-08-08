"""Quick-capture inbox: capture, the pure triage rules, and each triage target."""

import io

import pytest

from app.services import inbox as svc
from app.services import inbox_triage as triage


@pytest.fixture(autouse=True)
def _uploads_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "UPLOAD_DIR", tmp_path / "inbox")


def _png_bytes() -> bytes:
    Image = pytest.importorskip("PIL.Image", reason="Pillow not installed")
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (90, 90, 90)).save(buf, format="PNG")
    return buf.getvalue()


def _capture(client, auth, text: str, source: str = "web") -> dict:
    res = client.post("/api/inbox", headers=auth, json={"text": text, "source": source})
    assert res.status_code == 201, res.text
    return res.json()


# --- the pure rules -------------------------------------------------------


def test_refs_round_trip():
    assert triage.make_ref("task", "abc") == "task:abc"
    assert triage.parse_ref("task:abc") == ("task", "abc")
    assert triage.make_ref("dismissed") == "dismissed"
    assert triage.parse_ref("dismissed") == ("dismissed", None)
    assert triage.parse_ref(None) == (None, None)


def test_an_unreadable_ref_reads_as_untriaged_rather_than_exploding():
    """A row from an older or newer version must not break the list endpoint."""
    assert triage.parse_ref("nonsense") == (None, None)
    assert triage.parse_ref("task:") == (None, None)
    assert triage.is_triaged("nonsense") is False


def test_a_reference_target_needs_an_id():
    for kind in ("task", "article", "event", "diary"):
        with pytest.raises(triage.TriageError):
            triage.make_ref(kind, "")
    with pytest.raises(triage.TriageError):
        triage.make_ref("unknown", "1")
    # An id containing the separator could not be parsed back apart.
    with pytest.raises(triage.TriageError):
        triage.make_ref("task", "a:b")


def test_an_item_is_triaged_once():
    triage.ensure_triageable(None)  # fine
    with pytest.raises(triage.TriageError):
        triage.ensure_triageable("task:abc")


def test_title_and_slug_come_from_the_text():
    assert triage.title_from_text("## Тау туралы\n\nойлар") == "Тау туралы"
    assert triage.title_from_text("\n\n  ") == "Атаусыз"
    # Cyrillic transliterates rather than vanishing.
    assert triage.slugify("Тау туралы") == "tau-turaly"
    assert triage.slugify("!!!") == "note"


# --- capture --------------------------------------------------------------


def test_capture_and_list_newest_first(client, auth):
    for text in ["first", "second", "third"]:
        _capture(client, auth, text)

    items = client.get("/api/inbox", headers=auth).json()
    assert [i["text"] for i in items] == ["third", "second", "first"]
    assert all(i["triaged_to"] is None for i in items)
    assert client.get("/api/inbox/count", headers=auth).json()["untriaged"] == 3


def test_capture_with_a_photo(client, auth):
    item = _capture(client, auth, "look at this")
    res = client.post(
        f"/api/inbox/{item['id']}/images",
        headers=auth,
        files={"files": ("photo.png", _png_bytes(), "image/png")},
    )
    assert res.status_code == 201
    image = res.json()[0]
    assert image["url"] == f"/api/inbox/images/{image['id']}"

    stored = client.get("/api/inbox", headers=auth).json()[0]
    assert [i["id"] for i in stored["images"]] == [image["id"]]
    assert client.get(f"/api/inbox/images/{image['id']}", headers=auth).status_code == 200

    # Deleting the item takes its files with it.
    assert client.delete(f"/api/inbox/{item['id']}", headers=auth).status_code == 204
    assert list(svc.UPLOAD_DIR.iterdir()) == []


def test_an_item_can_be_photo_only(client, auth):
    item = _capture(client, auth, "")
    assert item["text"] == ""


# --- triage ---------------------------------------------------------------


def test_triage_to_task_creates_one_and_marks_the_item(client, auth):
    item = _capture(client, auth, "Renew the domain")

    res = client.post(
        f"/api/inbox/{item['id']}/triage",
        headers=auth,
        json={"kind": "task", "due_at": "2026-08-20"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "task"

    task = next(t for t in client.get("/api/tasks", headers=auth).json() if t["id"] == body["target_id"])
    assert task["title"] == "Renew the domain"
    assert task["due_at"] == "2026-08-20"
    # Attribution for later phases.
    assert task["source"] == "inbox"

    assert body["item"]["triaged_kind"] == "task"
    assert body["item"]["triaged_id"] == task["id"]
    # And it leaves the untriaged list.
    assert client.get("/api/inbox?triaged=false", headers=auth).json() == []
    assert client.get("/api/inbox/count", headers=auth).json()["untriaged"] == 0
    assert len(client.get("/api/inbox?triaged=true", headers=auth).json()) == 1


def test_triage_to_event_needs_a_start_and_creates_one(client, auth):
    item = _capture(client, auth, "Coffee with Madina")

    missing = client.post(
        f"/api/inbox/{item['id']}/triage", headers=auth, json={"kind": "event"}
    )
    assert missing.status_code == 409
    # The failure left it in the inbox, which is the recoverable direction.
    assert client.get("/api/inbox/count", headers=auth).json()["untriaged"] == 1

    res = client.post(
        f"/api/inbox/{item['id']}/triage",
        headers=auth,
        json={"kind": "event", "starts_at": "2026-08-20T14:30:00", "reminder_minutes": 30},
    )
    assert res.status_code == 200
    events = client.get("/api/calendar/events", headers=auth).json()
    assert [e["title"] for e in events] == ["Coffee with Madina"]
    assert events[0]["starts_at"] == "2026-08-20T14:30:00+05:00"
    assert events[0]["reminder_minutes"] == 30


def test_triage_to_article_creates_a_private_draft(client, auth):
    item = _capture(client, auth, "# Тау туралы\n\nойларым осында")

    res = client.post(f"/api/inbox/{item['id']}/triage", headers=auth, json={"kind": "article"})
    assert res.status_code == 200
    slug = res.json()["target_id"]

    article = client.get(f"/api/articles/{slug}", headers=auth).json()
    assert article["title"] == "Тау туралы"
    assert article["body_md"] == "# Тау туралы\n\nойларым осында"
    # A captured thought is not a published post.
    assert article["visibility"] == "private"


def test_two_articles_from_similar_text_get_distinct_slugs(client, auth):
    first = _capture(client, auth, "Same headline")
    second = _capture(client, auth, "Same headline")

    slug_a = client.post(f"/api/inbox/{first['id']}/triage", headers=auth, json={"kind": "article"}).json()["target_id"]
    slug_b = client.post(f"/api/inbox/{second['id']}/triage", headers=auth, json={"kind": "article"}).json()["target_id"]
    assert slug_a != slug_b


def test_triage_to_diary_appends_rather_than_replacing(client, auth):
    from app.services import diary as diary_svc

    day = diary_svc.today()
    client.put(f"/api/diary/entries/{day}", headers=auth, json={"body_md": "already written"})

    item = _capture(client, auth, "one more thought")
    res = client.post(f"/api/inbox/{item['id']}/triage", headers=auth, json={"kind": "diary"})
    assert res.status_code == 200
    assert res.json()["target_id"] == day

    entry = client.get(f"/api/diary/entries/{day}", headers=auth).json()
    assert entry["body_md"] == "already written\n\n---\n\none more thought"


def test_triage_to_diary_on_an_empty_day_adds_no_separator(client, auth):
    item = _capture(client, auth, "first thought of the day")
    client.post(f"/api/inbox/{item['id']}/triage", headers=auth, json={"kind": "diary"})

    from app.services import diary as diary_svc

    entry = client.get(f"/api/diary/entries/{diary_svc.today()}", headers=auth).json()
    assert entry["body_md"] == "first thought of the day"


def test_dismiss_is_a_recorded_outcome(client, auth):
    item = _capture(client, auth, "never mind")
    res = client.post(f"/api/inbox/{item['id']}/triage", headers=auth, json={"kind": "dismissed"})
    assert res.status_code == 200
    assert res.json()["item"]["triaged_kind"] == "dismissed"
    assert res.json()["target_id"] is None
    assert client.get("/api/inbox/count", headers=auth).json()["untriaged"] == 0


def test_an_item_cannot_be_triaged_twice(client, auth):
    item = _capture(client, auth, "once")
    client.post(f"/api/inbox/{item['id']}/triage", headers=auth, json={"kind": "task"})

    again = client.post(f"/api/inbox/{item['id']}/triage", headers=auth, json={"kind": "dismissed"})
    assert again.status_code == 409
    # Only one task was ever created.
    assert len(client.get("/api/tasks", headers=auth).json()) == 1


def test_unknown_triage_target_is_refused(client, auth):
    item = _capture(client, auth, "hmm")
    res = client.post(f"/api/inbox/{item['id']}/triage", headers=auth, json={"kind": "banana"})
    assert res.status_code == 409


def test_a_telegram_item_keeps_its_attribution_through_triage(client, auth):
    """Forward-compatible with phase 3."""
    item = _capture(client, auth, "from my phone", source="telegram")
    res = client.post(f"/api/inbox/{item['id']}/triage", headers=auth, json={"kind": "task"})
    task = client.get("/api/tasks", headers=auth).json()[0]
    assert task["source"] == "inbox:telegram"
    assert res.json()["item"]["source"] == "telegram"


def test_inbox_is_admin_only(client, auth):
    item = _capture(client, auth, "private thought")
    image_id = client.post(
        f"/api/inbox/{item['id']}/images",
        headers=auth,
        files={"files": ("photo.png", _png_bytes(), "image/png")},
    ).json()[0]["id"]

    anon = client.__class__(client.app)
    assert anon.get("/api/inbox").status_code == 401
    assert anon.get("/api/inbox/count").status_code == 401
    assert anon.post("/api/inbox", json={"text": "x"}).status_code == 401
    assert anon.post(f"/api/inbox/{item['id']}/triage", json={"kind": "task"}).status_code == 401
    assert anon.delete(f"/api/inbox/{item['id']}").status_code == 401
    assert anon.get(f"/api/inbox/images/{image_id}").status_code == 401
