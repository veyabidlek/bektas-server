"""Reading list: public to read, admin-only to write, plus the CSV parsers.

The parsing half needs no database — it is where a Notion export actually
bites (a group header, ⭐ with a variation selector, "TBD" in a numeric
column, a BOM), so it is tested as plain functions on plain strings.
"""

import dataclasses
import io

import pytest

from app.services import reading_covers as covers_svc
from scripts import import_reading as csv_import


@pytest.fixture(autouse=True)
def _uploads_in_tmp(tmp_path, monkeypatch):
    """Never write test covers onto the real volume."""
    monkeypatch.setattr(covers_svc, "UPLOAD_DIR", tmp_path / "reading")


def _png_bytes(size=(40, 30), color=(90, 40, 20)) -> bytes:
    Image = pytest.importorskip("PIL.Image", reason="Pillow not installed")
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _book(client, auth, **fields):
    body = {"title": "A book"} | fields
    res = client.post("/api/reading", headers=auth, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _upload_cover(client, auth, item_id, size=(40, 30)):
    return client.post(
        f"/api/reading/{item_id}/cover",
        headers=auth,
        files={"file": ("cover.png", _png_bytes(size), "image/png")},
    )


# --- the API ---------------------------------------------------------------


def test_reading_list_is_public(client, auth):
    """The whole point is a page a logged-out visitor can read. (A touched
    status — the default not_started backlog is admin-only, tested below.)"""
    _book(client, auth, title="Deep Work", author="Cal Newport", status="completed")

    anon = client.__class__(client.app)
    res = anon.get("/api/reading")
    assert res.status_code == 200
    assert [i["title"] for i in res.json()["items"]] == ["Deep Work"]


def test_not_started_backlog_is_admin_only(client, auth):
    """The backlog is the owner's business ("only in admin", 2026-08-10):
    a visitor sees only books that have actually been touched."""
    _book(client, auth, title="Someday Maybe", status="not_started")
    _book(client, auth, title="Open Book", status="in_progress")

    anon = client.__class__(client.app)
    public_titles = [i["title"] for i in anon.get("/api/reading").json()["items"]]
    assert public_titles == ["Open Book"]

    admin_titles = [
        i["title"] for i in client.get("/api/reading", headers=auth).json()["items"]
    ]
    assert set(admin_titles) == {"Someday Maybe", "Open Book"}


def test_writes_are_admin_only(client):
    anon = client.__class__(client.app)
    assert anon.post("/api/reading", json={"title": "x"}).status_code == 401
    assert anon.put("/api/reading/1", json={"title": "x"}).status_code == 401
    assert anon.delete("/api/reading/1").status_code == 401


def test_crud_round_trip(client, auth):
    created = _book(
        client,
        auth,
        title="  Martin Eden  ",
        author="Jack London",
        category="Novel",
        status="completed",
        pages=480,
        score=5,
        started="2025-06-13",
        completed="2025-07-05",
    )
    assert created["title"] == "Martin Eden"  # trimmed
    assert created["started"] == "2025-06-13"
    assert created["created_at"]

    updated = client.put(
        f"/api/reading/{created['id']}",
        headers=auth,
        json={"title": "Martin Eden", "status": "in_progress", "author": "Jack London"},
    )
    assert updated.status_code == 200
    # PUT replaces: fields left out of the body are cleared, not preserved.
    assert updated.json()["status"] == "in_progress"
    assert updated.json()["completed"] is None
    assert updated.json()["score"] is None

    assert client.delete(f"/api/reading/{created['id']}", headers=auth).status_code == 204
    assert client.get("/api/reading").json()["items"] == []


def test_missing_item_is_404_not_a_crash(client, auth):
    assert client.put("/api/reading/999", headers=auth, json={"title": "x"}).status_code == 404
    assert client.delete("/api/reading/999", headers=auth).status_code == 404


def test_finished_books_come_first_and_unread_ones_last(client, auth):
    _book(client, auth, title="Older", status="completed", completed="2020-05-05")
    _book(client, auth, title="Unread", status="not_started")
    _book(client, auth, title="Newest", status="completed", completed="2025-02-12")

    listed = client.get("/api/reading").json()["items"]
    assert [i["title"] for i in listed] == ["Newest", "Older", "Unread"]


def test_optional_fields_default_to_nothing(client, auth):
    item = _book(client, auth, title="Just added")
    assert item["status"] == "not_started"
    assert item["author"] is None
    assert item["category"] is None
    assert item["score"] is None
    assert item["pages"] is None
    assert item["started"] is None and item["completed"] is None
    assert item["description"] is None
    assert item["cover_url"] is None


# --- the shelf: description ------------------------------------------------


def test_a_description_round_trips_through_create_list_and_update(client, auth):
    created = _book(
        client, auth, title="Shoe Dog", status="completed", description="Nike, from a car boot."
    )
    assert created["description"] == "Nike, from a car boot."

    listed = client.get("/api/reading").json()["items"]
    assert listed[0]["description"] == "Nike, from a car boot."

    edited = client.put(
        f"/api/reading/{created['id']}",
        headers=auth,
        json={"title": "Shoe Dog", "status": "completed", "description": "Rewritten."},
    )
    assert edited.json()["description"] == "Rewritten."


def test_a_blank_description_is_stored_as_nothing(client, auth):
    """A textarea sends ""; the card must not render an empty blurb."""
    assert _book(client, auth, description="   ")["description"] is None


def test_a_put_without_a_description_clears_it(client, auth):
    """PUT is a full replace and the client sends the whole object, so an
    omitted blurb means "removed", not "unchanged"."""
    created = _book(client, auth, title="Shoe Dog", description="Nike, from a car boot.")

    cleared = client.put(
        f"/api/reading/{created['id']}", headers=auth, json={"title": "Shoe Dog"}
    )
    assert cleared.json()["description"] is None


# --- covers ----------------------------------------------------------------


def test_a_cover_is_public_the_way_a_portfolio_screenshot_is(client, auth):
    """The one that would hurt if it broke. /reading is a page a logged-out
    visitor can read, so its covers have to load without a cookie — the
    portfolio's exception, not the Islam shelf's rule."""
    item = _book(client, auth, status="completed")
    assert _upload_cover(client, auth, item["id"]).status_code == 200

    anon = client.__class__(client.app)
    res = anon.get(f"/api/reading/covers/{item['id']}")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/")
    assert res.headers["cache-control"] == "public, max-age=86400"


def test_uploading_a_cover_is_admin_only(client, auth):
    item = _book(client, auth)
    anon = client.__class__(client.app)
    assert anon.post(f"/api/reading/{item['id']}/cover").status_code == 401


def test_the_covers_route_is_not_swallowed_by_the_item_routes(client, auth):
    """`/api/reading/covers/{id}` puts the literal "covers" where an int item
    id goes. Nothing captures it today, and this is what says so if a
    `GET /{item_id}` is ever added above it — the shape both routes share is
    exactly the collision."""
    item = _book(client, auth, status="completed")
    _upload_cover(client, auth, item["id"])

    anon = client.__class__(client.app)
    assert anon.get(f"/api/reading/covers/{item['id']}").status_code == 200
    # And the ordinary item routes still resolve.
    assert anon.get("/api/reading").status_code == 200
    assert client.put(
        f"/api/reading/{item['id']}", headers=auth, json={"title": "Renamed"}
    ).status_code == 200


def test_a_cover_is_downscaled_and_exposed_as_a_url(client, auth):
    item = _book(client, auth)
    res = _upload_cover(client, auth, item["id"], size=(3000, 2000))
    assert res.status_code == 200
    assert res.json()["cover_url"] == f"/api/reading/covers/{item['id']}"

    assert len(list(covers_svc.UPLOAD_DIR.iterdir())) == 1
    stored = next(covers_svc.UPLOAD_DIR.iterdir())
    Image = pytest.importorskip("PIL.Image", reason="Pillow not installed")
    assert max(Image.open(stored).size) <= 1600


def test_replacing_a_cover_takes_the_old_file_off_the_volume(client, auth):
    item = _book(client, auth)
    _upload_cover(client, auth, item["id"])
    first = next(covers_svc.UPLOAD_DIR.iterdir()).name

    _upload_cover(client, auth, item["id"], size=(60, 60))
    files = [p.name for p in covers_svc.UPLOAD_DIR.iterdir()]
    # A fresh name, and exactly one file: reusing the path would leave a cached
    # browser showing the previous picture.
    assert len(files) == 1 and files[0] != first


def test_a_put_never_touches_the_cover(client, auth):
    """The cover does not travel in the PUT body, so a full replace has nothing
    to replace it with — editing a title must not throw the picture away."""
    item = _book(client, auth, description="blurb")
    _upload_cover(client, auth, item["id"])

    edited = client.put(f"/api/reading/{item['id']}", headers=auth, json={"title": "Renamed"})
    assert edited.status_code == 200
    assert edited.json()["cover_url"] == f"/api/reading/covers/{item['id']}"
    assert edited.json()["description"] is None  # this one *is* replaced
    assert len(list(covers_svc.UPLOAD_DIR.iterdir())) == 1


def test_a_book_without_a_cover_serves_a_404_not_a_500(client, auth):
    item = _book(client, auth, status="completed")
    anon = client.__class__(client.app)
    assert anon.get(f"/api/reading/covers/{item['id']}").status_code == 404
    assert anon.get("/api/reading/covers/999").status_code == 404


def test_a_non_image_cover_is_rejected(client, auth):
    item = _book(client, auth)
    res = client.post(
        f"/api/reading/{item['id']}/cover",
        headers=auth,
        files={"file": ("notes.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert res.status_code == 415


def test_deleting_an_item_takes_its_cover_off_the_disk(client, auth):
    item = _book(client, auth)
    _upload_cover(client, auth, item["id"])
    assert len(list(covers_svc.UPLOAD_DIR.iterdir())) == 1

    assert client.delete(f"/api/reading/{item['id']}", headers=auth).status_code == 204
    assert list(covers_svc.UPLOAD_DIR.iterdir()) == []


# --- notes and sessions ----------------------------------------------------


def _note(client, auth, item_id, **fields):
    body = {"date": "2026-08-09", "body_md": "A thought."} | fields
    res = client.post(f"/api/reading/{item_id}/notes", headers=auth, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _session(client, auth, item_id, **fields):
    body = {"date": "2026-08-09", "pages": 30} | fields
    res = client.post(f"/api/reading/{item_id}/sessions", headers=auth, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def test_notes_and_sessions_are_admin_only(client, auth):
    """The shelf is public; the reading log is not. An anonymous GET on either
    has to be a 401, not a peek at what he thought about the book."""
    item = _book(client, auth, status="completed")
    anon = client.__class__(client.app)

    assert anon.get(f"/api/reading/{item['id']}/notes").status_code == 401
    assert anon.post(f"/api/reading/{item['id']}/notes", json={}).status_code == 401
    assert anon.delete(f"/api/reading/{item['id']}/notes/1").status_code == 401
    assert anon.get(f"/api/reading/{item['id']}/sessions").status_code == 401
    assert anon.post(f"/api/reading/{item['id']}/sessions", json={}).status_code == 401
    assert anon.delete(f"/api/reading/{item['id']}/sessions/1").status_code == 401


def test_a_note_round_trips_and_carries_its_item_id(client, auth):
    item = _book(client, auth)
    created = _note(client, auth, item["id"], page_from=10, page_to=24, body_md="On focus.")

    assert created["item_id"] == item["id"]
    assert (created["page_from"], created["page_to"]) == (10, 24)
    assert created["body_md"] == "On focus."

    listed = client.get(f"/api/reading/{item['id']}/notes", headers=auth).json()["items"]
    assert [n["id"] for n in listed] == [created["id"]]


def test_a_note_body_takes_camel_case_as_the_client_sends_it(client, auth):
    """`lib/api.ts` does not snake-case outgoing bodies — both spellings land."""
    item = _book(client, auth)
    res = client.post(
        f"/api/reading/{item['id']}/notes",
        headers=auth,
        json={"date": "2026-08-09", "pageFrom": 3, "pageTo": 9, "bodyMd": "camel"},
    )
    assert res.status_code == 201, res.text
    assert (res.json()["page_from"], res.json()["page_to"]) == (3, 9)
    assert res.json()["body_md"] == "camel"


def test_a_page_range_has_to_read_forwards(client, auth):
    item = _book(client, auth)

    def post(**fields):
        return client.post(
            f"/api/reading/{item['id']}/notes",
            headers=auth,
            json={"date": "2026-08-09"} | fields,
        ).status_code

    assert post(page_from=40, page_to=12) == 422
    assert post(page_from=0) == 422
    # One-sided ranges are legitimate — "from page 12 onwards", or no range.
    assert post(page_from=12) == 201
    assert post(page_to=12) == 201
    assert post(page_from=12, page_to=12) == 201
    assert post() == 201
    # And the date is the one format this codebase has.
    assert post(date="09/08/2026") == 422


def test_notes_and_sessions_come_back_newest_date_first(client, auth):
    item = _book(client, auth)
    _note(client, auth, item["id"], date="2026-08-01", body_md="older")
    _note(client, auth, item["id"], date="2026-08-09", body_md="newer")
    _session(client, auth, item["id"], date="2026-08-01", pages=5)
    _session(client, auth, item["id"], date="2026-08-09", pages=50)

    notes = client.get(f"/api/reading/{item['id']}/notes", headers=auth).json()["items"]
    assert [n["body_md"] for n in notes] == ["newer", "older"]

    sessions = client.get(f"/api/reading/{item['id']}/sessions", headers=auth).json()["items"]
    assert [s["pages"] for s in sessions] == [50, 5]


def test_a_session_round_trips_with_optional_minutes(client, auth):
    item = _book(client, auth)
    timed = _session(client, auth, item["id"], pages=42, minutes=55)
    assert (timed["item_id"], timed["pages"], timed["minutes"]) == (item["id"], 42, 55)

    untimed = _session(client, auth, item["id"], pages=3)
    assert untimed["minutes"] is None

    assert client.post(
        f"/api/reading/{item['id']}/sessions",
        headers=auth,
        json={"date": "2026-08-09", "pages": -1},
    ).status_code == 422


def test_deleting_a_note_or_session_is_scoped_to_its_book(client, auth):
    item = _book(client, auth)
    other = _book(client, auth, title="Another")
    note = _note(client, auth, item["id"])
    session = _session(client, auth, item["id"])

    # The right id under the wrong book deletes nothing.
    assert client.delete(
        f"/api/reading/{other['id']}/notes/{note['id']}", headers=auth
    ).status_code == 404
    assert client.delete(
        f"/api/reading/{other['id']}/sessions/{session['id']}", headers=auth
    ).status_code == 404

    assert client.delete(
        f"/api/reading/{item['id']}/notes/{note['id']}", headers=auth
    ).status_code == 204
    assert client.delete(
        f"/api/reading/{item['id']}/sessions/{session['id']}", headers=auth
    ).status_code == 204
    assert client.get(f"/api/reading/{item['id']}/notes", headers=auth).json()["items"] == []
    assert client.get(f"/api/reading/{item['id']}/sessions", headers=auth).json()["items"] == []


def test_logs_on_a_missing_book_are_404(client, auth):
    assert client.get("/api/reading/999/notes", headers=auth).status_code == 404
    assert client.get("/api/reading/999/sessions", headers=auth).status_code == 404
    assert client.post(
        "/api/reading/999/notes", headers=auth, json={"date": "2026-08-09"}
    ).status_code == 404


def test_deleting_a_book_cascades_its_notes_and_sessions(client, auth):
    item = _book(client, auth)
    kept = _book(client, auth, title="Kept")
    _note(client, auth, item["id"])
    _note(client, auth, kept["id"])
    _session(client, auth, item["id"])

    assert client.delete(f"/api/reading/{item['id']}", headers=auth).status_code == 204
    assert len(client.get(f"/api/reading/{kept['id']}/notes", headers=auth).json()["items"]) == 1

    from app.database import SessionLocal
    from app.models.reading import ReadingNote, ReadingSession

    session = SessionLocal()
    try:
        assert session.query(ReadingNote).filter_by(item_id=item["id"]).count() == 0
        assert session.query(ReadingSession).filter_by(item_id=item["id"]).count() == 0
    finally:
        session.close()


def test_blank_author_is_stored_as_nothing(client, auth):
    """A form sends ""; the client must not have to render an empty author."""
    assert _book(client, auth, author="   ", category="")["author"] is None


def test_validation_rejects_bad_scores_statuses_and_dates(client, auth):
    def post(**fields):
        return client.post("/api/reading", headers=auth, json={"title": "x"} | fields).status_code

    assert post(score=6) == 422
    assert post(score=0) == 422
    assert post(status="reading") == 422
    assert post(completed="12/03/2024") == 422
    assert post(started="not-a-date") == 422
    assert client.post("/api/reading", headers=auth, json={"title": "   "}).status_code == 422

    # The edges of the allowed ranges are fine.
    assert post(score=1) == 201
    assert post(score=5) == 201
    for status in ("not_started", "in_progress", "completed", "abandoned"):
        assert post(status=status) == 201


# --- the CSV parsers -------------------------------------------------------


def test_progress_maps_to_the_four_statuses():
    assert csv_import.parse_status("Not started") == "not_started"
    assert csv_import.parse_status("In progress") == "in_progress"
    assert csv_import.parse_status("Completed") == "completed"
    assert csv_import.parse_status("could not finish") == "abandoned"
    # Case and padding are Notion's business, not ours.
    assert csv_import.parse_status("  COMPLETED ") == "completed"
    # An unknown or empty select must never fail the import.
    assert csv_import.parse_status("") == "not_started"
    assert csv_import.parse_status("Shelved") == "not_started"
    assert csv_import.parse_status(None) == "not_started"


def test_score_counts_stars_and_ignores_the_variation_selector():
    assert csv_import.parse_score("⭐️⭐️⭐️⭐️⭐️") == 5
    assert csv_import.parse_score("⭐⭐⭐") == 3
    assert csv_import.parse_score("") is None
    assert csv_import.parse_score("TBD") is None
    assert csv_import.parse_score(None) is None


def test_dates_parse_notion_s_long_form():
    assert csv_import.parse_date("February 8, 2024") == "2024-02-08"
    assert csv_import.parse_date("January 1, 2019") == "2019-01-01"
    assert csv_import.parse_date("  December 19, 2025 ") == "2025-12-19"
    assert csv_import.parse_date("") is None
    assert csv_import.parse_date(None) is None
    # One malformed cell must not cost the whole import.
    assert csv_import.parse_date("8 Feb 2024") is None


def test_pages_are_optional_integers():
    assert csv_import.parse_pages("211") == 211
    assert csv_import.parse_pages("") is None
    assert csv_import.parse_pages("many") is None


def test_the_books_group_header_is_not_a_book():
    header = {"Name": "Books", "Progress": "Not started"}
    assert csv_import.is_group_header(header) is True
    assert csv_import.parse_row(header) is None

    # A real book that happens to be called "Books" still imports.
    real = {"Name": "Books", "Author": "Someone", "Progress": "Completed"}
    assert csv_import.is_group_header(real) is False
    assert csv_import.parse_row(real) is not None


def test_a_row_without_a_name_is_skipped():
    assert csv_import.parse_row({"Name": "", "Progress": "Completed"}) is None
    assert csv_import.parse_row({"Name": "   "}) is None


def test_a_full_row_parses_into_every_field():
    row = csv_import.parse_row(
        {
            "Name": "How to Become a Straight A Student 🅰️",
            "Author": "Cal Newport",
            "Completed": "February 8, 2024",
            "Day Count": "31",
            "Progress": "Completed",
            "Score": "⭐️⭐️⭐️⭐️⭐️",
            "Started": "January 8, 2024",
            "Type": "Self-Development",
            "pages": "211",
        }
    )
    assert row == csv_import.ReadingRow(
        title="How to Become a Straight A Student 🅰️",  # emoji kept
        author="Cal Newport",
        category="Self-Development",
        status="completed",
        pages=211,
        score=5,
        started="2024-01-08",
        completed="2024-02-08",
    )


def test_a_bare_row_leaves_everything_empty():
    row = csv_import.parse_row(
        {"Name": "Why We Sleep 💤 ", "Progress": "Not started", "Type": "Self-Development"}
    )
    assert row.title == "Why We Sleep 💤"  # trailing space trimmed
    assert row.author is None
    assert row.status == "not_started"
    assert (row.score, row.pages, row.started, row.completed) == (None, None, None, None)


def test_parse_csv_handles_the_bom_and_drops_the_header_row(tmp_path):
    """Written with a BOM, exactly as Notion exports it."""
    path = tmp_path / "reading.csv"
    path.write_text(
        "Name,Author,Completed,Day Count,Progress,Score,Started,Type,pages\n"
        "Books,,,,Not started,,,,\n"
        "The Little Prince,Antoine de Saint-Exupéry,\"February 11, 2024\",1,Completed,"
        "⭐️⭐️⭐️⭐️⭐️,\"February 10, 2024\",Novel,109\n"
        ",,,,Not started,,,,\n",
        encoding="utf-8-sig",
    )

    rows = csv_import.parse_csv(path)
    assert [r.title for r in rows] == ["The Little Prince"]
    assert rows[0].author == "Antoine de Saint-Exupéry"
    assert rows[0].score == 5


def test_import_is_idempotent_and_case_insensitive(db, tmp_path):
    path = tmp_path / "reading.csv"
    path.write_text(
        "Name,Author,Completed,Day Count,Progress,Score,Started,Type,pages\n"
        "Clean Code,,,,Not started,,,Programming,\n"
        "Atomic Habits,,\"January 1, 2021\",,Completed,⭐️⭐️⭐️⭐️⭐️,,Self-Development,\n",
        encoding="utf-8-sig",
    )
    rows = csv_import.parse_csv(path)

    assert csv_import.import_rows(db, rows) == (2, 0)
    # Same file again: nothing new, nothing duplicated.
    assert csv_import.import_rows(db, rows) == (0, 2)

    # A title differing only in case is the same book. The real export has such
    # a pair ("Чистый код" / "Чистый Код"), so this is not a hypothetical.
    shouting = dataclasses.replace(rows[0], title="CLEAN CODE")
    assert csv_import.import_rows(db, [shouting]) == (0, 1)

    # Two rows of the same book inside one file collapse to one, too — the
    # seen-set grows as the import goes.
    fresh = dataclasses.replace(rows[0], title="Refactoring UI")
    assert csv_import.import_rows(db, [fresh, dataclasses.replace(fresh, title="refactoring ui")]) == (1, 1)

    from app.services import reading as svc

    assert sorted(i.title for i in svc.list_reading_items(db)) == [
        "Atomic Habits",
        "Clean Code",
        "Refactoring UI",
    ]
