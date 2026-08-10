"""The Islam shelf: books, covers, notes and sessions.

The one that would hurt if it broke: a cover is **admin-only**. The portfolio's
public-image exception exists because a project card is public content — nothing
in this section is, so an anonymous GET on a cover has to be a 401.
"""

import io

import pytest

from app.services import islam_covers as covers_svc


@pytest.fixture(autouse=True)
def _uploads_in_tmp(tmp_path, monkeypatch):
    """Never write test covers onto the real volume."""
    monkeypatch.setattr(covers_svc, "UPLOAD_DIR", tmp_path / "islam")


def _png_bytes(size=(40, 30), color=(20, 120, 90)) -> bytes:
    Image = pytest.importorskip("PIL.Image", reason="Pillow not installed")
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _book(client, auth, **fields):
    body = {"title": "Riyad as-Salihin"} | fields
    res = client.post("/api/islam/books", headers=auth, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _upload_cover(client, auth, book_id, size=(40, 30)):
    return client.post(
        f"/api/islam/books/{book_id}/cover",
        headers=auth,
        files={"file": ("cover.png", _png_bytes(size), "image/png")},
    )


# --- admin-gated ----------------------------------------------------------


def test_every_book_route_is_admin_only(client, auth):
    book = _book(client, auth)
    anon = client.__class__(client.app)

    assert anon.get("/api/islam/books").status_code == 401
    assert anon.post("/api/islam/books", json={"title": "x"}).status_code == 401
    assert anon.patch(f"/api/islam/books/{book['id']}", json={"title": "x"}).status_code == 401
    assert anon.delete(f"/api/islam/books/{book['id']}").status_code == 401
    assert anon.post(f"/api/islam/books/{book['id']}/cover").status_code == 401
    assert anon.get(f"/api/islam/books/{book['id']}/notes").status_code == 401
    assert anon.post(f"/api/islam/books/{book['id']}/notes", json={}).status_code == 401
    assert anon.delete(f"/api/islam/books/{book['id']}/notes/x").status_code == 401
    assert anon.get(f"/api/islam/books/{book['id']}/sessions").status_code == 401
    assert anon.post(f"/api/islam/books/{book['id']}/sessions", json={}).status_code == 401
    assert anon.delete(f"/api/islam/books/{book['id']}/sessions/x").status_code == 401


def test_a_cover_is_not_public_the_way_a_portfolio_screenshot_is(client, auth):
    """The whole reason this section serves its own images."""
    book = _book(client, auth)
    assert _upload_cover(client, auth, book["id"]).status_code == 200

    anon = client.__class__(client.app)
    assert anon.get(f"/api/islam/books/covers/{book['id']}").status_code == 401

    res = client.get(f"/api/islam/books/covers/{book['id']}", headers=auth)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/")
    assert "private" in res.headers.get("cache-control", "")


# --- the shelf ------------------------------------------------------------


def test_a_new_book_is_reading_and_has_no_cover(client, auth):
    book = _book(client, auth, author="an-Nawawi")
    assert book["status"] == "reading"
    assert book["cover_url"] is None
    assert book["author"] == "an-Nawawi"
    assert book["total_pages"] is None


def test_books_are_listed_newest_first(client, auth):
    _book(client, auth, title="First")
    _book(client, auth, title="Second")
    items = client.get("/api/islam/books", headers=auth).json()["items"]
    assert [b["title"] for b in items] == ["Second", "First"]


def test_patch_is_partial(client, auth):
    book = _book(client, auth, author="an-Nawawi", total_pages=500)
    patched = client.patch(
        f"/api/islam/books/{book['id']}", headers=auth, json={"status": "finished"}
    ).json()
    assert patched["status"] == "finished"
    assert patched["author"] == "an-Nawawi"
    assert patched["total_pages"] == 500

    # And camelCase lands too — lib/api.ts sends `totalPages`.
    patched = client.patch(
        f"/api/islam/books/{book['id']}", headers=auth, json={"totalPages": 480}
    ).json()
    assert patched["total_pages"] == 480


def test_an_unknown_status_is_refused(client, auth):
    res = client.post("/api/islam/books", headers=auth, json={"title": "x", "status": "read"})
    assert res.status_code == 422


def test_a_title_is_required(client, auth):
    assert client.post("/api/islam/books", headers=auth, json={"title": "  "}).status_code == 422


def test_missing_books_404(client, auth):
    assert client.patch("/api/islam/books/nope", headers=auth, json={"title": "x"}).status_code == 404
    assert client.delete("/api/islam/books/nope", headers=auth).status_code == 404
    assert client.get("/api/islam/books/nope/notes", headers=auth).status_code == 404
    assert client.get("/api/islam/books/covers/nope", headers=auth).status_code == 404


# --- covers ---------------------------------------------------------------


def test_a_cover_is_downscaled_and_exposed_as_a_url(client, auth):
    book = _book(client, auth)
    res = _upload_cover(client, auth, book["id"], size=(3000, 2000))
    assert res.status_code == 200, res.text
    assert res.json()["cover_url"] == f"/api/islam/books/covers/{book['id']}"

    assert len(list(covers_svc.UPLOAD_DIR.iterdir())) == 1
    stored = next(covers_svc.UPLOAD_DIR.iterdir())
    Image = pytest.importorskip("PIL.Image", reason="Pillow not installed")
    with Image.open(stored) as im:
        assert max(im.size) == 1600


def test_replacing_a_cover_takes_the_old_file_off_the_volume(client, auth):
    book = _book(client, auth)
    _upload_cover(client, auth, book["id"])
    first = next(covers_svc.UPLOAD_DIR.iterdir()).name

    _upload_cover(client, auth, book["id"], size=(60, 60))
    files = [p.name for p in covers_svc.UPLOAD_DIR.iterdir()]
    assert len(files) == 1
    assert files[0] != first  # a new name, so a cached browser cannot keep the old one


def test_a_non_image_cover_is_rejected(client, auth):
    book = _book(client, auth)
    res = client.post(
        f"/api/islam/books/{book['id']}/cover",
        headers=auth,
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert res.status_code == 415


def test_a_book_without_a_cover_serves_a_404_not_a_500(client, auth):
    book = _book(client, auth)
    assert client.get(f"/api/islam/books/covers/{book['id']}", headers=auth).status_code == 404


def test_deleting_a_book_takes_its_cover_off_the_disk(client, auth):
    book = _book(client, auth)
    _upload_cover(client, auth, book["id"])
    assert len(list(covers_svc.UPLOAD_DIR.iterdir())) == 1

    assert client.delete(f"/api/islam/books/{book['id']}", headers=auth).status_code == 204
    assert list(covers_svc.UPLOAD_DIR.iterdir()) == []


# --- notes ----------------------------------------------------------------


def _note(client, auth, book_id, **fields):
    body = {"date": "2026-08-10", "body_md": "A thought"} | fields
    return client.post(f"/api/islam/books/{book_id}/notes", headers=auth, json=body)


def test_notes_round_trip_newest_date_first(client, auth):
    book = _book(client, auth)
    _note(client, auth, book["id"], date="2026-08-01")
    _note(client, auth, book["id"], date="2026-08-09", page_from=12, page_to=18)

    items = client.get(f"/api/islam/books/{book['id']}/notes", headers=auth).json()["items"]
    assert [n["date"] for n in items] == ["2026-08-09", "2026-08-01"]
    assert items[0]["page_from"] == 12 and items[0]["page_to"] == 18
    assert items[1]["page_from"] is None


def test_a_backwards_note_page_range_is_refused(client, auth):
    book = _book(client, auth)
    assert _note(client, auth, book["id"], page_from=18, page_to=12).status_code == 422
    # A one-sided range is legitimate — "from page 12 onwards".
    assert _note(client, auth, book["id"], page_from=12).status_code == 201
    assert _note(client, auth, book["id"], page_to=12).status_code == 201


def test_a_note_needs_a_real_date(client, auth):
    book = _book(client, auth)
    assert _note(client, auth, book["id"], date="10.08.2026").status_code == 422


def test_deleting_a_note(client, auth):
    book = _book(client, auth)
    note = _note(client, auth, book["id"]).json()
    assert client.delete(
        f"/api/islam/books/{book['id']}/notes/{note['id']}", headers=auth
    ).status_code == 204
    assert client.delete(
        f"/api/islam/books/{book['id']}/notes/{note['id']}", headers=auth
    ).status_code == 404


def test_a_note_cannot_be_deleted_through_another_book(client, auth):
    book = _book(client, auth)
    other = _book(client, auth, title="Other")
    note = _note(client, auth, book["id"]).json()

    assert client.delete(
        f"/api/islam/books/{other['id']}/notes/{note['id']}", headers=auth
    ).status_code == 404
    assert len(client.get(f"/api/islam/books/{book['id']}/notes", headers=auth).json()["items"]) == 1


# --- sessions -------------------------------------------------------------


def test_sessions_round_trip_newest_first(client, auth):
    book = _book(client, auth)
    client.post(
        f"/api/islam/books/{book['id']}/sessions",
        headers=auth,
        json={"date": "2026-08-01", "pages": 10},
    )
    res = client.post(
        f"/api/islam/books/{book['id']}/sessions",
        headers=auth,
        json={"date": "2026-08-09", "pages": 25, "minutes": 40},
    )
    assert res.status_code == 201, res.text

    items = client.get(f"/api/islam/books/{book['id']}/sessions", headers=auth).json()["items"]
    assert [s["date"] for s in items] == ["2026-08-09", "2026-08-01"]
    assert items[0]["pages"] == 25 and items[0]["minutes"] == 40
    assert items[1]["minutes"] is None

    assert client.delete(
        f"/api/islam/books/{book['id']}/sessions/{items[0]['id']}", headers=auth
    ).status_code == 204
    assert len(client.get(f"/api/islam/books/{book['id']}/sessions", headers=auth).json()["items"]) == 1


def test_deleting_a_book_cascades_its_notes_and_sessions(client, auth):
    book = _book(client, auth)
    kept = _book(client, auth, title="Kept")
    _note(client, auth, book["id"])
    _note(client, auth, kept["id"])
    client.post(
        f"/api/islam/books/{book['id']}/sessions",
        headers=auth,
        json={"date": "2026-08-09", "pages": 5},
    )

    assert client.delete(f"/api/islam/books/{book['id']}", headers=auth).status_code == 204
    assert len(client.get(f"/api/islam/books/{kept['id']}/notes", headers=auth).json()["items"]) == 1

    from app.models.islam_media import IslamBookNote, IslamBookSession
    from app.database import SessionLocal

    session = SessionLocal()
    try:
        assert session.query(IslamBookNote).filter_by(book_id=book["id"]).count() == 0
        assert session.query(IslamBookSession).filter_by(book_id=book["id"]).count() == 0
    finally:
        session.close()
