"""Diary: one entry per day, private photos, admin-only everywhere."""

import io

import pytest

from app.services import diary as svc


@pytest.fixture(autouse=True)
def _uploads_in_tmp(tmp_path, monkeypatch):
    """Never write test photos onto the real volume."""
    monkeypatch.setattr(svc, "UPLOAD_DIR", tmp_path / "diary")


def _png_bytes(size=(40, 30), color=(200, 30, 30)) -> bytes:
    Image = pytest.importorskip("PIL.Image", reason="Pillow not installed")
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def test_unwritten_day_returns_an_empty_shell_not_a_404(client, auth):
    """The editor opens on any date, so a missing day is 200 with exists=false."""
    res = client.get("/api/diary/entries/2026-08-01", headers=auth)
    assert res.status_code == 200
    body = res.json()
    assert body["exists"] is False
    assert body["body_md"] == ""
    assert body["images"] == []


def test_writing_the_same_day_twice_edits_it(client, auth):
    first = client.put(
        "/api/diary/entries/2026-08-05", headers=auth, json={"body_md": "first draft"}
    )
    assert first.status_code == 200
    assert first.json()["exists"] is True

    second = client.put(
        "/api/diary/entries/2026-08-05", headers=auth, json={"body_md": "# second\n\nbetter"}
    )
    assert second.status_code == 200
    assert second.json()["body_md"] == "# second\n\nbetter"

    # One row, not two.
    listed = client.get("/api/diary/entries", headers=auth).json()
    assert [e["day"] for e in listed] == ["2026-08-05"]


def test_entries_are_listed_newest_first_with_a_clean_preview(client, auth):
    for day, body in [
        ("2026-08-02", "# Heading\n\nWent to the [lake](http://x.com) today"),
        ("2026-08-04", "Short one"),
        ("2026-08-03", "![photo](/api/diary/images/abc) with a picture"),
    ]:
        client.put(f"/api/diary/entries/{day}", headers=auth, json={"body_md": body})

    listed = client.get("/api/diary/entries", headers=auth).json()
    assert [e["day"] for e in listed] == ["2026-08-04", "2026-08-03", "2026-08-02"]

    previews = {e["day"]: e["preview"] for e in listed}
    # Markdown noise is stripped so the preview reads like prose.
    assert previews["2026-08-02"] == "Heading Went to the lake today"
    assert previews["2026-08-03"] == "with a picture"


def test_today_endpoint_tracks_the_dashboard_card_states(client, auth):
    today = svc.today()

    before = client.get("/api/diary/today", headers=auth).json()
    assert before["day"] == today
    assert before["exists"] is False  # card prompts him to write

    client.put(f"/api/diary/entries/{today}", headers=auth, json={"body_md": "done today"})

    after = client.get("/api/diary/today", headers=auth).json()
    assert after["exists"] is True  # card shows the done state
    assert after["body_md"] == "done today"


def test_photo_upload_round_trip_and_private_serving(client, auth):
    day = "2026-08-06"
    upload = client.post(
        f"/api/diary/entries/{day}/images",
        headers=auth,
        files={"files": ("photo.png", _png_bytes(), "image/png")},
    )
    assert upload.status_code == 201, upload.text
    image = upload.json()[0]
    assert image["width"] == 40 and image["height"] == 30

    # Attaching a photo creates the day even though nothing was written yet.
    entry = client.get(f"/api/diary/entries/{day}", headers=auth).json()
    assert entry["exists"] is True
    assert [i["id"] for i in entry["images"]] == [image["id"]]

    served = client.get(f"/api/diary/images/{image['id']}", headers=auth)
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("image/")
    assert "private" in served.headers.get("cache-control", "")

    assert client.delete(f"/api/diary/images/{image['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/diary/images/{image['id']}", headers=auth).status_code == 404


def test_uploads_are_downscaled(client, auth):
    """A big photo must not be stored at phone resolution."""
    pytest.importorskip("PIL.Image", reason="Pillow not installed")
    big = _png_bytes(size=(3000, 2000))

    res = client.post(
        "/api/diary/entries/2026-08-07/images",
        headers=auth,
        files={"files": ("big.png", big, "image/png")},
    )
    assert res.status_code == 201
    image = res.json()[0]
    assert max(image["width"], image["height"]) == 1600


def test_rejects_a_non_image_and_a_bad_day(client, auth):
    bad_type = client.post(
        "/api/diary/entries/2026-08-08/images",
        headers=auth,
        files={"files": ("notes.txt", b"hello", "text/plain")},
    )
    assert bad_type.status_code == 415

    assert client.get("/api/diary/entries/08-2026", headers=auth).status_code == 422
    assert (
        client.put(
            "/api/diary/entries/not-a-day", headers=auth, json={"body_md": "x"}
        ).status_code
        == 422
    )


def test_deleting_a_day_removes_its_photos_from_disk(client, auth):
    day = "2026-08-09"
    upload = client.post(
        f"/api/diary/entries/{day}/images",
        headers=auth,
        files={"files": ("photo.png", _png_bytes(), "image/png")},
    )
    image_id = upload.json()[0]["id"]
    stored = list(svc.UPLOAD_DIR.iterdir())
    assert len(stored) == 1

    assert client.delete(f"/api/diary/entries/{day}", headers=auth).status_code == 204
    assert list(svc.UPLOAD_DIR.iterdir()) == []
    assert client.get(f"/api/diary/images/{image_id}", headers=auth).status_code == 404


def test_everything_is_admin_only_including_the_images(client, auth):
    """The photos are as private as the words."""
    day = "2026-08-10"
    upload = client.post(
        f"/api/diary/entries/{day}/images",
        headers=auth,
        files={"files": ("photo.png", _png_bytes(), "image/png")},
    )
    image_id = upload.json()[0]["id"]

    # A fresh anonymous client — no header, no cookie.
    anon = client.__class__(client.app)
    assert anon.get("/api/diary/today").status_code == 401
    assert anon.get("/api/diary/entries").status_code == 401
    assert anon.get(f"/api/diary/entries/{day}").status_code == 401
    assert anon.put(f"/api/diary/entries/{day}", json={"body_md": "x"}).status_code == 401
    assert anon.delete(f"/api/diary/entries/{day}").status_code == 401
    assert anon.get(f"/api/diary/images/{image_id}").status_code == 401
    assert anon.delete(f"/api/diary/images/{image_id}").status_code == 401
    assert anon.post(f"/api/diary/entries/{day}/images").status_code == 401


def test_entry_title_is_optional_and_survives_a_rewrite(client, auth):
    day = "2026-08-14"

    # An entry is worth writing without a title.
    untitled = client.put(
        f"/api/diary/entries/{day}", headers=auth, json={"body_md": "no title here"}
    ).json()
    assert untitled["title"] == ""

    titled = client.put(
        f"/api/diary/entries/{day}",
        headers=auth,
        json={"title": "  Тау  ", "body_md": "no title here"},
    ).json()
    assert titled["title"] == "Тау"  # trimmed

    assert client.get(f"/api/diary/entries/{day}", headers=auth).json()["title"] == "Тау"
    # And it reaches the list the past-entries view and dashboard card read.
    listed = client.get("/api/diary/entries", headers=auth).json()
    assert listed[0]["title"] == "Тау"


def test_title_can_be_cleared(client, auth):
    day = "2026-08-15"
    client.put(f"/api/diary/entries/{day}", headers=auth, json={"title": "x", "body_md": "b"})
    cleared = client.put(
        f"/api/diary/entries/{day}", headers=auth, json={"title": "", "body_md": "b"}
    ).json()
    assert cleared["title"] == ""
