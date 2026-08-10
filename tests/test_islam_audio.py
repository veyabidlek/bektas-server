"""The audio shelf — the books' twin, tested where it differs.

`kind`, the free-text position on a note, minute-only sessions, and the same
admin-gated cover serving. The shared shapes are exercised here too rather than
trusted: books and audio are two tables, so a mirror can drift.
"""

import io

import pytest

from app.services import islam_covers as covers_svc


@pytest.fixture(autouse=True)
def _uploads_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(covers_svc, "UPLOAD_DIR", tmp_path / "islam")


def _png_bytes(size=(40, 30)) -> bytes:
    Image = pytest.importorskip("PIL.Image", reason="Pillow not installed")
    buf = io.BytesIO()
    Image.new("RGB", size, (90, 60, 160)).save(buf, format="PNG")
    return buf.getvalue()


def _audio(client, auth, **fields):
    body = {"title": "Seerah series", "kind": "playlist"} | fields
    res = client.post("/api/islam/audio", headers=auth, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _upload_cover(client, auth, audio_id, size=(40, 30)):
    return client.post(
        f"/api/islam/audio/{audio_id}/cover",
        headers=auth,
        files={"file": ("cover.png", _png_bytes(size), "image/png")},
    )


# --- admin-gated ----------------------------------------------------------


def test_every_audio_route_is_admin_only(client, auth):
    audio = _audio(client, auth)
    anon = client.__class__(client.app)

    assert anon.get("/api/islam/audio").status_code == 401
    assert anon.post("/api/islam/audio", json={"title": "x", "kind": "playlist"}).status_code == 401
    assert anon.patch(f"/api/islam/audio/{audio['id']}", json={"title": "x"}).status_code == 401
    assert anon.delete(f"/api/islam/audio/{audio['id']}").status_code == 401
    assert anon.post(f"/api/islam/audio/{audio['id']}/cover").status_code == 401
    assert anon.get(f"/api/islam/audio/{audio['id']}/notes").status_code == 401
    assert anon.post(f"/api/islam/audio/{audio['id']}/notes", json={}).status_code == 401
    assert anon.delete(f"/api/islam/audio/{audio['id']}/notes/x").status_code == 401
    assert anon.get(f"/api/islam/audio/{audio['id']}/sessions").status_code == 401
    assert anon.post(f"/api/islam/audio/{audio['id']}/sessions", json={}).status_code == 401
    assert anon.delete(f"/api/islam/audio/{audio['id']}/sessions/x").status_code == 401


def test_an_audio_cover_is_admin_only_too(client, auth):
    audio = _audio(client, auth)
    assert _upload_cover(client, auth, audio["id"]).status_code == 200

    anon = client.__class__(client.app)
    assert anon.get(f"/api/islam/audio/covers/{audio['id']}").status_code == 401

    res = client.get(f"/api/islam/audio/covers/{audio['id']}", headers=auth)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/")
    assert "private" in res.headers.get("cache-control", "")


# --- the shelf ------------------------------------------------------------


def test_an_audio_item_carries_its_kind_and_defaults_to_reading(client, auth):
    audio = _audio(client, auth, kind="audiobook", creator="Sh. Abdullah")
    assert audio["kind"] == "audiobook"
    assert audio["status"] == "reading"
    assert audio["creator"] == "Sh. Abdullah"
    assert audio["cover_url"] is None


def test_an_unknown_kind_or_status_is_refused(client, auth):
    assert client.post(
        "/api/islam/audio", headers=auth, json={"title": "x", "kind": "podcast"}
    ).status_code == 422
    assert client.post(
        "/api/islam/audio", headers=auth, json={"title": "x", "kind": "playlist", "status": "done"}
    ).status_code == 422


def test_audio_is_listed_newest_first_and_patches_partially(client, auth):
    _audio(client, auth, title="First")
    second = _audio(client, auth, title="Second", creator="A reciter")

    items = client.get("/api/islam/audio", headers=auth).json()["items"]
    assert [a["title"] for a in items] == ["Second", "First"]

    patched = client.patch(
        f"/api/islam/audio/{second['id']}", headers=auth, json={"status": "finished"}
    ).json()
    assert patched["status"] == "finished"
    assert patched["creator"] == "A reciter"
    assert patched["kind"] == "playlist"


def test_missing_audio_404s(client, auth):
    assert client.patch("/api/islam/audio/nope", headers=auth, json={"title": "x"}).status_code == 404
    assert client.delete("/api/islam/audio/nope", headers=auth).status_code == 404
    assert client.get("/api/islam/audio/nope/notes", headers=auth).status_code == 404
    assert client.get("/api/islam/audio/covers/nope", headers=auth).status_code == 404


# --- covers ---------------------------------------------------------------


def test_an_audio_cover_is_downscaled_and_replaceable(client, auth):
    audio = _audio(client, auth)
    res = _upload_cover(client, auth, audio["id"], size=(2400, 2400))
    assert res.json()["cover_url"] == f"/api/islam/audio/covers/{audio['id']}"

    stored = next(covers_svc.UPLOAD_DIR.iterdir())
    Image = pytest.importorskip("PIL.Image", reason="Pillow not installed")
    with Image.open(stored) as im:
        assert max(im.size) == 1600

    _upload_cover(client, auth, audio["id"], size=(50, 50))
    files = [p.name for p in covers_svc.UPLOAD_DIR.iterdir()]
    assert len(files) == 1 and files[0] != stored.name


def test_deleting_an_audio_item_takes_its_cover_with_it(client, auth):
    audio = _audio(client, auth)
    _upload_cover(client, auth, audio["id"])
    assert client.delete(f"/api/islam/audio/{audio['id']}", headers=auth).status_code == 204
    assert list(covers_svc.UPLOAD_DIR.iterdir()) == []


def test_a_non_image_cover_is_rejected(client, auth):
    audio = _audio(client, auth)
    res = client.post(
        f"/api/islam/audio/{audio['id']}/cover",
        headers=auth,
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert res.status_code == 415


# --- notes and sessions ---------------------------------------------------


def test_a_note_keeps_its_position_as_free_text(client, auth):
    audio = _audio(client, auth)
    for position in ("episode 3", "1:12:00", None):
        res = client.post(
            f"/api/islam/audio/{audio['id']}/notes",
            headers=auth,
            json={"date": "2026-08-09", "position": position, "body_md": "note"},
        )
        assert res.status_code == 201, res.text
        assert res.json()["position"] == position


def test_audio_notes_read_newest_date_first_and_delete(client, auth):
    audio = _audio(client, auth)
    for date in ("2026-08-01", "2026-08-09", "2026-08-05"):
        client.post(
            f"/api/islam/audio/{audio['id']}/notes",
            headers=auth,
            json={"date": date, "body_md": date},
        )

    items = client.get(f"/api/islam/audio/{audio['id']}/notes", headers=auth).json()["items"]
    assert [n["date"] for n in items] == ["2026-08-09", "2026-08-05", "2026-08-01"]

    assert client.delete(
        f"/api/islam/audio/{audio['id']}/notes/{items[0]['id']}", headers=auth
    ).status_code == 204
    assert client.delete(
        f"/api/islam/audio/{audio['id']}/notes/{items[0]['id']}", headers=auth
    ).status_code == 404


def test_a_note_needs_a_real_date(client, auth):
    audio = _audio(client, auth)
    res = client.post(
        f"/api/islam/audio/{audio['id']}/notes",
        headers=auth,
        json={"date": "yesterday", "body_md": "x"},
    )
    assert res.status_code == 422


def test_listening_sessions_count_minutes_only(client, auth):
    audio = _audio(client, auth)
    res = client.post(
        f"/api/islam/audio/{audio['id']}/sessions",
        headers=auth,
        json={"date": "2026-08-09", "minutes": 45},
    )
    assert res.status_code == 201, res.text
    assert res.json()["minutes"] == 45
    assert "pages" not in res.json()

    client.post(
        f"/api/islam/audio/{audio['id']}/sessions",
        headers=auth,
        json={"date": "2026-08-01", "minutes": 20},
    )
    items = client.get(f"/api/islam/audio/{audio['id']}/sessions", headers=auth).json()["items"]
    assert [s["date"] for s in items] == ["2026-08-09", "2026-08-01"]

    assert client.delete(
        f"/api/islam/audio/{audio['id']}/sessions/{items[0]['id']}", headers=auth
    ).status_code == 204
    assert len(
        client.get(f"/api/islam/audio/{audio['id']}/sessions", headers=auth).json()["items"]
    ) == 1


def test_deleting_an_audio_item_cascades_its_notes_and_sessions(client, auth):
    audio = _audio(client, auth)
    kept = _audio(client, auth, title="Kept")
    for target in (audio, kept):
        client.post(
            f"/api/islam/audio/{target['id']}/notes",
            headers=auth,
            json={"date": "2026-08-09", "body_md": "x"},
        )
    client.post(
        f"/api/islam/audio/{audio['id']}/sessions",
        headers=auth,
        json={"date": "2026-08-09", "minutes": 10},
    )

    assert client.delete(f"/api/islam/audio/{audio['id']}", headers=auth).status_code == 204
    assert len(client.get(f"/api/islam/audio/{kept['id']}/notes", headers=auth).json()["items"]) == 1

    from app.database import SessionLocal
    from app.models.islam_media import IslamAudioNote, IslamAudioSession

    session = SessionLocal()
    try:
        assert session.query(IslamAudioNote).filter_by(audio_id=audio["id"]).count() == 0
        assert session.query(IslamAudioSession).filter_by(audio_id=audio["id"]).count() == 0
    finally:
        session.close()


def test_a_note_cannot_be_deleted_through_another_audio_item(client, auth):
    audio = _audio(client, auth)
    other = _audio(client, auth, title="Other")
    note = client.post(
        f"/api/islam/audio/{audio['id']}/notes",
        headers=auth,
        json={"date": "2026-08-09", "body_md": "x"},
    ).json()

    assert client.delete(
        f"/api/islam/audio/{other['id']}/notes/{note['id']}", headers=auth
    ).status_code == 404
