"""Wikilink backlinks — `[[slug]]` mentions between writings.

The one thing that must never happen: a private writing showing up in a
public reader's "Mentioned in" panel just because it links to a public one.
"""


def _article(client, auth, slug: str, body_md: str = "hello", visibility: str = "public"):
    res = client.post(
        "/api/articles",
        headers=auth,
        json={
            "slug": slug,
            "title": slug,
            "description": "d",
            "date": "2026-08-08",
            "read_time": "1 min",
            "body_md": body_md,
            "visibility": visibility,
        },
    )
    assert res.status_code == 201, res.text
    return slug


def test_backlinks_find_exact_and_labelled_mentions(client, auth):
    _article(client, auth, "target")
    _article(client, auth, "plain", body_md="see [[target]] for more")
    _article(client, auth, "labelled", body_md="see [[target|this one]] too")
    _article(client, auth, "unrelated", body_md="no links here")

    res = client.get("/api/articles/target/backlinks", headers=auth)
    assert res.status_code == 200
    assert {a["slug"] for a in res.json()} == {"plain", "labelled"}


def test_a_longer_slug_is_not_a_false_positive(client, auth):
    _article(client, auth, "note")
    _article(client, auth, "other", body_md="links [[note-2]] only")

    res = client.get("/api/articles/note/backlinks", headers=auth)
    assert res.json() == []


def test_the_article_never_mentions_itself(client, auth):
    _article(client, auth, "selfie", body_md="I am [[selfie]]")

    res = client.get("/api/articles/selfie/backlinks", headers=auth)
    assert res.json() == []


def test_private_sources_stay_out_of_a_public_reader_s_panel(client, auth):
    _article(client, auth, "target")
    _article(client, auth, "secret", body_md="ref [[target]]", visibility="private")
    _article(client, auth, "open", body_md="ref [[target]]")

    anon = client.__class__(client.app)
    public = anon.get("/api/articles/target/backlinks")
    assert public.status_code == 200
    assert {a["slug"] for a in public.json()} == {"open"}

    admin = client.get("/api/articles/target/backlinks", headers=auth)
    assert {a["slug"] for a in admin.json()} == {"open", "secret"}


def test_an_invisible_target_404s_rather_than_confirming_it_exists(client, auth):
    _article(client, auth, "hidden", visibility="private")

    anon = client.__class__(client.app)
    assert anon.get("/api/articles/hidden/backlinks").status_code == 404
