"""Khatms, the reading log and sura notes.

The load-bearing claims: `pages_logged` is computed rather than stored (so it
cannot survive a deleted entry), a page range that reads backwards or off the
end of the mushaf is refused, and none of it is reachable without the admin key.
"""


def _khatm(client, auth, **fields):
    body = {"name": "Ramadan khatm", "kind": "individual"} | fields
    res = client.post("/api/islam/khatms", headers=auth, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _log(client, auth, khatm_id, page_from, page_to, date="2026-08-10", **fields):
    body = {
        "khatm_id": khatm_id,
        "date": date,
        "page_from": page_from,
        "page_to": page_to,
    } | fields
    return client.post("/api/islam/quran-log", headers=auth, json=body)


# --- everything is admin-only --------------------------------------------


def test_the_whole_quran_half_is_admin_only(client):
    anon = client.__class__(client.app)
    assert anon.get("/api/islam/khatms").status_code == 401
    assert anon.post("/api/islam/khatms", json={"name": "x", "kind": "individual"}).status_code == 401
    assert anon.patch("/api/islam/khatms/abc", json={"name": "y"}).status_code == 401
    assert anon.delete("/api/islam/khatms/abc").status_code == 401
    assert anon.get("/api/islam/quran-log").status_code == 401
    assert anon.post("/api/islam/quran-log", json={}).status_code == 401
    assert anon.delete("/api/islam/quran-log/abc").status_code == 401
    assert anon.get("/api/islam/sura-notes").status_code == 401
    assert anon.put("/api/islam/sura-notes/2", json={"body_md": "x"}).status_code == 401
    assert anon.delete("/api/islam/sura-notes/2").status_code == 401


# --- khatms ---------------------------------------------------------------


def test_a_new_khatm_starts_empty_at_the_full_mushaf(client, auth):
    khatm = _khatm(client, auth, name="My own")
    assert khatm["target_pages"] == 604
    assert khatm["pages_logged"] == 0
    assert khatm["completed_at"] is None
    assert khatm["portion"] is None
    assert khatm["started_at"]


def test_several_khatms_run_at_once_active_first_then_newest(client, auth):
    first = _khatm(client, auth, name="First")
    second = _khatm(client, auth, name="Second")
    shared = _khatm(client, auth, name="Group", kind="shared", portion="juz 5")

    # Finishing one drops it below the running ones.
    client.patch(
        f"/api/islam/khatms/{second['id']}",
        headers=auth,
        json={"completed_at": "2026-08-09T20:00:00+05:00"},
    )

    items = client.get("/api/islam/khatms", headers=auth).json()["items"]
    assert [i["name"] for i in items][:2] == ["Group", "First"]
    assert items[-1]["name"] == "Second"
    assert items[0]["kind"] == "shared" and items[0]["portion"] == "juz 5"
    assert first["id"] in [i["id"] for i in items]


def test_a_shared_khatm_keeps_its_portion_as_free_text(client, auth):
    khatm = _khatm(client, auth, kind="shared", portion="pages 81-100")
    assert khatm["portion"] == "pages 81-100"

    patched = client.patch(
        f"/api/islam/khatms/{khatm['id']}", headers=auth, json={"portion": "Ya-Sin"}
    )
    assert patched.status_code == 200
    assert patched.json()["portion"] == "Ya-Sin"


def test_patch_is_partial_and_can_reopen_a_finished_khatm(client, auth):
    khatm = _khatm(client, auth, name="Ramadan")
    client.patch(
        f"/api/islam/khatms/{khatm['id']}",
        headers=auth,
        json={"completed_at": "2026-08-09T20:00:00+05:00"},
    )

    # Renaming must not disturb the completion…
    renamed = client.patch(
        f"/api/islam/khatms/{khatm['id']}", headers=auth, json={"name": "Ramadan 2026"}
    ).json()
    assert renamed["name"] == "Ramadan 2026"
    assert renamed["completed_at"] == "2026-08-09T20:00:00+05:00"

    # …and an explicit null re-opens it.
    reopened = client.patch(
        f"/api/islam/khatms/{khatm['id']}", headers=auth, json={"completed_at": None}
    ).json()
    assert reopened["completed_at"] is None


def test_an_unknown_kind_is_refused(client, auth):
    res = client.post(
        "/api/islam/khatms", headers=auth, json={"name": "x", "kind": "collective"}
    )
    assert res.status_code == 422


def test_missing_khatms_404_rather_than_500(client, auth):
    assert client.patch(
        "/api/islam/khatms/nope", headers=auth, json={"name": "x"}
    ).status_code == 404
    assert client.delete("/api/islam/khatms/nope", headers=auth).status_code == 404


# --- pages_logged is computed, not stored ---------------------------------


def test_pages_logged_is_the_sum_of_inclusive_ranges(client, auth):
    khatm = _khatm(client, auth)
    assert _log(client, auth, khatm["id"], 1, 20).status_code == 201
    assert _log(client, auth, khatm["id"], 21, 21, date="2026-08-11").status_code == 201

    items = client.get("/api/islam/khatms", headers=auth).json()["items"]
    # 20 pages + the single page 21 — an inclusive range counts both ends.
    assert items[0]["pages_logged"] == 21


def test_deleting_an_entry_takes_its_pages_back(client, auth):
    """The point of not storing a counter: it cannot drift."""
    khatm = _khatm(client, auth)
    entry = _log(client, auth, khatm["id"], 1, 10).json()
    _log(client, auth, khatm["id"], 11, 15)

    assert client.get("/api/islam/khatms", headers=auth).json()["items"][0]["pages_logged"] == 15

    assert client.delete(f"/api/islam/quran-log/{entry['id']}", headers=auth).status_code == 204
    assert client.get("/api/islam/khatms", headers=auth).json()["items"][0]["pages_logged"] == 5


def test_each_khatm_counts_only_its_own_pages(client, auth):
    a = _khatm(client, auth, name="A")
    b = _khatm(client, auth, name="B")
    _log(client, auth, a["id"], 1, 100)
    _log(client, auth, b["id"], 1, 5)

    by_name = {i["name"]: i["pages_logged"] for i in client.get("/api/islam/khatms", headers=auth).json()["items"]}
    assert by_name == {"A": 100, "B": 5}


def test_deleting_a_khatm_cascades_its_log(client, auth):
    khatm = _khatm(client, auth)
    _log(client, auth, khatm["id"], 1, 10)
    other = _khatm(client, auth, name="Kept")
    _log(client, auth, other["id"], 1, 3)

    assert client.delete(f"/api/islam/khatms/{khatm['id']}", headers=auth).status_code == 204

    remaining = client.get("/api/islam/quran-log", headers=auth).json()["items"]
    assert [e["khatm_id"] for e in remaining] == [other["id"]]


# --- the log --------------------------------------------------------------


def test_the_log_reads_newest_date_first_and_filters_by_khatm(client, auth):
    a = _khatm(client, auth, name="A")
    b = _khatm(client, auth, name="B")
    _log(client, auth, a["id"], 1, 5, date="2026-08-01")
    _log(client, auth, a["id"], 6, 10, date="2026-08-05")
    _log(client, auth, b["id"], 1, 2, date="2026-08-03")

    everything = client.get("/api/islam/quran-log", headers=auth).json()["items"]
    assert [e["date"] for e in everything] == ["2026-08-05", "2026-08-03", "2026-08-01"]

    only_a = client.get(f"/api/islam/quran-log?khatm={a['id']}", headers=auth).json()["items"]
    assert [e["date"] for e in only_a] == ["2026-08-05", "2026-08-01"]


def test_a_backwards_range_is_refused(client, auth):
    khatm = _khatm(client, auth)
    assert _log(client, auth, khatm["id"], 20, 5).status_code == 422


def test_a_page_past_the_end_of_the_mushaf_is_refused(client, auth):
    khatm = _khatm(client, auth)
    assert _log(client, auth, khatm["id"], 600, 605).status_code == 422
    assert _log(client, auth, khatm["id"], 0, 10).status_code == 422
    # 604 itself is fine — it is the last page, not one past it.
    assert _log(client, auth, khatm["id"], 604, 604).status_code == 201


def test_logging_against_a_khatm_that_is_not_there_is_a_404(client, auth):
    assert _log(client, auth, "no-such-khatm", 1, 5).status_code == 404


def test_a_note_rides_along_with_the_entry(client, auth):
    khatm = _khatm(client, auth)
    entry = _log(client, auth, khatm["id"], 1, 5, note="Tafsir of al-Baqara").json()
    assert entry["note"] == "Tafsir of al-Baqara"

    blank = _log(client, auth, khatm["id"], 6, 7, note="   ").json()
    assert blank["note"] is None


def test_deleting_an_absent_log_entry_is_a_404(client, auth):
    assert client.delete("/api/islam/quran-log/nope", headers=auth).status_code == 404


def test_the_client_s_camelcase_body_is_accepted_too(client, auth):
    """lib/api.ts sends `khatmId` / `pageFrom` / `pageTo` / `targetPages` — the
    outgoing bodies are not snake-cased there. Both spellings have to land."""
    created = client.post(
        "/api/islam/khatms",
        headers=auth,
        json={"name": "Camel", "kind": "individual", "targetPages": 300},
    )
    assert created.status_code == 201, created.text
    assert created.json()["target_pages"] == 300

    logged = client.post(
        "/api/islam/quran-log",
        headers=auth,
        json={
            "khatmId": created.json()["id"],
            "date": "2026-08-10",
            "pageFrom": 1,
            "pageTo": 30,
        },
    )
    assert logged.status_code == 201, logged.text
    assert logged.json()["page_to"] == 30


# --- sura notes -----------------------------------------------------------


def test_a_sura_note_upserts_rather_than_duplicating(client, auth):
    first = client.put("/api/islam/sura-notes/2", headers=auth, json={"body_md": "first pass"})
    assert first.status_code == 200
    assert first.json()["surah"] == 2

    second = client.put("/api/islam/sura-notes/2", headers=auth, json={"body_md": "# better"})
    assert second.status_code == 200
    assert second.json()["body_md"] == "# better"

    items = client.get("/api/islam/sura-notes", headers=auth).json()["items"]
    assert [n["surah"] for n in items] == [2]


def test_sura_notes_are_listed_in_mushaf_order(client, auth):
    for surah in (114, 1, 36):
        client.put(f"/api/islam/sura-notes/{surah}", headers=auth, json={"body_md": "x"})

    items = client.get("/api/islam/sura-notes", headers=auth).json()["items"]
    assert [n["surah"] for n in items] == [1, 36, 114]


def test_surah_numbers_outside_the_mushaf_are_refused(client, auth):
    assert client.put("/api/islam/sura-notes/0", headers=auth, json={"body_md": "x"}).status_code == 422
    assert client.put("/api/islam/sura-notes/115", headers=auth, json={"body_md": "x"}).status_code == 422
    assert client.delete("/api/islam/sura-notes/115", headers=auth).status_code == 422
    # The two ends are inside.
    assert client.put("/api/islam/sura-notes/1", headers=auth, json={"body_md": "x"}).status_code == 200
    assert client.put("/api/islam/sura-notes/114", headers=auth, json={"body_md": "x"}).status_code == 200


def test_deleting_a_sura_note(client, auth):
    client.put("/api/islam/sura-notes/18", headers=auth, json={"body_md": "al-Kahf"})
    assert client.delete("/api/islam/sura-notes/18", headers=auth).status_code == 204
    assert client.get("/api/islam/sura-notes", headers=auth).json()["items"] == []
    assert client.delete("/api/islam/sura-notes/18", headers=auth).status_code == 404
