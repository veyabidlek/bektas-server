"""Photos on writings — and above all, that they inherit the writing's visibility.

A leak here is the worst kind: the article itself would 404 correctly while its
pictures stayed readable by URL.
"""

import io

import pytest

from app.dependencies import can_view
from app.services import article_images as svc


@pytest.fixture(autouse=True)
def _uploads_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "UPLOAD_DIR", tmp_path / "articles")


def _png_bytes(size=(40, 30)) -> bytes:
    Image = pytest.importorskip("PIL.Image", reason="Pillow not installed")
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


def _article(client, auth, slug: str, visibility: str) -> str:
    res = client.post(
        "/api/articles",
        headers=auth,
        json={
            "slug": slug,
            "title": slug,
            "description": "d",
            "date": "2026-08-08",
            "read_time": "1 min",
            "body_md": "hello",
            "visibility": visibility,
        },
    )
    assert res.status_code == 201, res.text
    return slug


def _attach(client, auth, slug: str) -> str:
    res = client.post(
        f"/api/articles/{slug}/images",
        headers=auth,
        files={"files": ("photo.png", _png_bytes(), "image/png")},
    )
    assert res.status_code == 201, res.text
    return res.json()[0]["id"]


def _friend_headers(client, auth) -> dict:
    """A real friend token, obtained the way the site issues one."""
    friend = client.post("/api/friends", headers=auth, json={"name": "Madina"}).json()
    token = client.post("/api/friends/login", json={"code": friend["code"]}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


# --- the pure rule --------------------------------------------------------


def test_can_view_matches_the_three_tiers():
    assert can_view("public", "public") is True
    assert can_view("public", "friend") is True
    assert can_view("public", "admin") is True

    assert can_view("friends", "public") is False
    assert can_view("friends", "friend") is True
    assert can_view("friends", "admin") is True

    assert can_view("private", "public") is False
    assert can_view("private", "friend") is False
    assert can_view("private", "admin") is True


def test_an_unknown_visibility_hides_rather_than_exposes():
    """A typo in the data must fail closed."""
    assert can_view("pubic", "public") is False
    assert can_view("", "friend") is False
    assert can_view("weird", "admin") is True


# --- the route mirrors it -------------------------------------------------


def test_a_public_writing_s_photo_loads_for_a_logged_out_reader(client, auth):
    slug = _article(client, auth, "public-post", "public")
    image_id = _attach(client, auth, slug)

    anon = client.__class__(client.app)
    res = anon.get(f"/api/articles/images/{image_id}")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/")
    # Public images may sit in a shared cache; gated ones may not.
    assert "public" in res.headers.get("cache-control", "")


def test_a_friends_writing_s_photo_needs_a_friend(client, auth):
    slug = _article(client, auth, "friends-post", "friends")
    image_id = _attach(client, auth, slug)

    anon = client.__class__(client.app)
    assert anon.get(f"/api/articles/images/{image_id}").status_code == 404

    friend = client.__class__(client.app)
    res = friend.get(f"/api/articles/images/{image_id}", headers=_friend_headers(client, auth))
    assert res.status_code == 200
    assert "private" in res.headers.get("cache-control", "")

    assert client.get(f"/api/articles/images/{image_id}", headers=auth).status_code == 200


def test_a_private_writing_s_photo_is_admin_only(client, auth):
    slug = _article(client, auth, "private-post", "private")
    image_id = _attach(client, auth, slug)

    anon = client.__class__(client.app)
    assert anon.get(f"/api/articles/images/{image_id}").status_code == 404

    friend = client.__class__(client.app)
    assert (
        friend.get(
            f"/api/articles/images/{image_id}", headers=_friend_headers(client, auth)
        ).status_code
        == 404
    )

    assert client.get(f"/api/articles/images/{image_id}", headers=auth).status_code == 200


def test_changing_the_writing_s_visibility_changes_its_photos(client, auth):
    """The mirroring has to be live, not copied at upload time."""
    slug = _article(client, auth, "moving-post", "public")
    image_id = _attach(client, auth, slug)

    anon = client.__class__(client.app)
    assert anon.get(f"/api/articles/images/{image_id}").status_code == 200

    client.put(f"/api/articles/{slug}", headers=auth, json={"visibility": "private"})
    assert anon.get(f"/api/articles/images/{image_id}").status_code == 404


def test_upload_and_delete_stay_admin_only(client, auth):
    slug = _article(client, auth, "guarded", "public")
    image_id = _attach(client, auth, slug)

    anon = client.__class__(client.app)
    assert anon.post(f"/api/articles/{slug}/images").status_code == 401
    assert anon.delete(f"/api/articles/images/{image_id}").status_code == 401

    assert client.delete(f"/api/articles/images/{image_id}", headers=auth).status_code == 204
    assert client.get(f"/api/articles/images/{image_id}", headers=auth).status_code == 404


def test_uploads_are_downscaled_and_listed(client, auth):
    slug = _article(client, auth, "big-post", "public")
    res = client.post(
        f"/api/articles/{slug}/images",
        headers=auth,
        files={"files": ("big.png", _png_bytes(size=(3000, 2000)), "image/png")},
    )
    assert res.status_code == 201
    image = res.json()[0]
    assert max(image["width"], image["height"]) == 1600
    # The URL is ready to paste straight into the markdown body.
    assert image["url"] == f"/api/articles/images/{image['id']}"

    listed = client.get(f"/api/articles/{slug}/images", headers=auth).json()
    assert [i["id"] for i in listed] == [image["id"]]


def test_a_non_image_is_rejected(client, auth):
    slug = _article(client, auth, "text-post", "public")
    res = client.post(
        f"/api/articles/{slug}/images",
        headers=auth,
        files={"files": ("notes.txt", b"hello", "text/plain")},
    )
    assert res.status_code == 415


def test_deleting_a_writing_takes_its_photos_off_the_disk(client, auth):
    """Fold-in: writings had no delete endpoint, so images could outlive nothing."""
    slug = _article(client, auth, "doomed", "public")
    image_id = _attach(client, auth, slug)
    assert len(list(svc.UPLOAD_DIR.iterdir())) == 1

    # A comment too, to prove the cascade covers them.
    client.post(f"/api/articles/{slug}/comments", json={"author": "A", "body": "hi"})

    assert client.delete(f"/api/articles/{slug}", headers=auth).status_code == 204
    assert client.get(f"/api/articles/{slug}", headers=auth).status_code == 404
    assert client.get(f"/api/articles/images/{image_id}", headers=auth).status_code == 404
    assert list(svc.UPLOAD_DIR.iterdir()) == []


def test_deleting_a_writing_is_admin_only_and_404s_when_absent(client, auth):
    anon = client.__class__(client.app)
    assert anon.delete("/api/articles/whatever").status_code == 401
    assert client.delete("/api/articles/does-not-exist", headers=auth).status_code == 404
