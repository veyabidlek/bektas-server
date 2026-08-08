"""The login path — the one thing that must not be subtly wrong."""

import json

from app.services import admin_key


def test_key_file_upload_logs_in(client, key_document):
    file_bytes = json.dumps(key_document).encode("utf-8")
    res = client.post(
        "/api/admin/login",
        files={"file": ("bekonai.key", file_bytes, "application/octet-stream")},
    )
    assert res.status_code == 200
    assert res.json()["token"]


def test_pasted_key_logs_in_the_same_way(client, key_document):
    """The paste path is the phone-friendly door — same credential, same result."""
    bare = client.post("/api/admin/login", data={"key": key_document["key"]})
    whole_file = client.post(
        "/api/admin/login", data={"key": json.dumps(key_document)}
    )
    assert bare.status_code == 200
    assert whole_file.status_code == 200


def test_login_sets_a_persistent_session_cookie(client, key_document):
    res = client.post("/api/admin/login", data={"key": key_document["key"]})
    cookie = res.headers["set-cookie"].lower()
    assert "bk_admin=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    # 30 days, the lifetime Bektas asked for.
    assert "max-age=2592000" in cookie
    # Secure is env-gated so local http development still works; the test env
    # turns it off, production leaves it on.
    assert "secure" not in cookie


def test_cookie_alone_authenticates(client, key_document):
    client.post("/api/admin/login", data={"key": key_document["key"]})
    # No Authorization header: the TestClient replays only the cookie jar.
    assert client.get("/api/admin/verify").json()["valid"] is True
    assert client.get("/api/calendar/events").status_code == 200


def test_wrong_key_is_rejected(client, key_document):
    for bad in ["", "not-a-key", json.dumps({"key": "wrong"}), "{malformed"]:
        res = client.post("/api/admin/login", data={"key": bad})
        assert res.status_code == 401, bad


def test_reissuing_revokes_the_previous_key(client, db, key_document):
    old = key_document["key"]
    new = admin_key.issue_key(db)["key"]

    assert client.post("/api/admin/login", data={"key": old}).status_code == 401
    assert client.post("/api/admin/login", data={"key": new}).status_code == 200


def test_extract_secret_handles_both_shapes():
    doc = {"v": 1, "key": "abc123"}
    assert admin_key.extract_secret(json.dumps(doc)) == "abc123"
    assert admin_key.extract_secret("  abc123\n") == "abc123"
    # A key pasted from a notes app that wrapped it across lines.
    assert admin_key.extract_secret("abc\n123") == "abc123"
    assert admin_key.extract_secret("") is None
    assert admin_key.extract_secret("{not json") is None


def test_admin_routes_still_reject_anonymous_callers(client):
    assert client.get("/api/calendar/events").status_code == 401
    assert client.get("/api/friends").status_code == 401
