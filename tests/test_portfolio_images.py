"""Hosted screenshots for the projects page.

Two things are worth pinning down here. First, the upload takes no project id —
the add-project form needs a URL before the project row exists, and if that ever
regresses the form has no way to work. Second, serving is *public*: unlike a
writing's photos, a project card's picture must load for a logged-out reader,
while upload and delete stay admin-only.
"""

import io

import pytest

from app.services import portfolio_images as svc


@pytest.fixture(autouse=True)
def _uploads_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "UPLOAD_DIR", tmp_path / "portfolio")


def _png_bytes(size=(40, 30)) -> bytes:
    Image = pytest.importorskip("PIL.Image", reason="Pillow not installed")
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


def _upload(client, auth) -> dict:
    res = client.post(
        "/api/portfolio/images",
        headers=auth,
        files={"files": ("shot.png", _png_bytes(), "image/png")},
    )
    assert res.status_code == 201, res.text
    return res.json()[0]


def test_an_upload_needs_no_project_and_returns_a_usable_url(client, auth):
    image = _upload(client, auth)
    assert image["url"] == f"/api/portfolio/images/{image['id']}"

    # The URL is what goes into screenshot_url, so it has to survive the round
    # trip through the project record unchanged.
    created = client.post(
        "/api/portfolio",
        headers=auth,
        json={"id": "p1", "title": "P1", "screenshot_url": image["url"]},
    )
    assert created.status_code == 201, created.text
    assert created.json()["screenshot_url"] == image["url"]


def test_a_screenshot_loads_for_a_logged_out_reader(client, auth):
    image = _upload(client, auth)

    anon = client.__class__(client.app)
    res = anon.get(image["url"])
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/")
    # Public content, so it may sit in a shared cache.
    assert "public" in res.headers.get("cache-control", "")


def test_upload_and_delete_stay_admin_only(client, auth):
    image = _upload(client, auth)

    anon = client.__class__(client.app)
    assert anon.post("/api/portfolio/images").status_code == 401
    assert anon.delete(f"/api/portfolio/images/{image['id']}").status_code == 401

    assert client.delete(f"/api/portfolio/images/{image['id']}", headers=auth).status_code == 204
    assert anon.get(image["url"]).status_code == 404
    assert list(svc.UPLOAD_DIR.iterdir()) == []


def test_uploads_are_downscaled(client, auth):
    res = client.post(
        "/api/portfolio/images",
        headers=auth,
        files={"files": ("big.png", _png_bytes(size=(3000, 2000)), "image/png")},
    )
    assert res.status_code == 201
    image = res.json()[0]
    assert max(image["width"], image["height"]) == 1600


def test_a_non_image_is_rejected(client, auth):
    res = client.post(
        "/api/portfolio/images",
        headers=auth,
        files={"files": ("notes.txt", b"hello", "text/plain")},
    )
    assert res.status_code == 415
    assert not svc.UPLOAD_DIR.exists() or list(svc.UPLOAD_DIR.iterdir()) == []


def test_deleting_an_absent_image_is_a_404(client, auth):
    assert client.delete("/api/portfolio/images/nope", headers=auth).status_code == 404
    assert client.get("/api/portfolio/images/nope").status_code == 404
