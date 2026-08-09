"""Universal search: index sync, the sanitizer, ranking, snippets and auth.

The sanitizer gets the most attention here. Everything else in this feature is
recoverable — a stale row, a snippet that reads oddly — but user text going into
a MATCH expression is the one place where a bad input could take the endpoint
down, so the nasty cases are pinned as executable statements.
"""

import pytest

from app.database import engine
from app.schemas.article import ArticleCreate
from app.schemas.calendar import CalendarEventCreate
from app.schemas.task import TaskCreate, TaskUpdate
from app.services import articles as articles_svc
from app.services import calendar as calendar_svc
from app.services import diary as diary_svc
from app.services import inbox as inbox_svc
from app.services import search as svc
from app.services import tasks as tasks_svc
from app.services.search import MARK_END, MARK_START, to_match_query
from app.services.search_index import (
    TABLE,
    drop_search_index,
    ensure_search_index,
    rebuild_search_index,
)


def refs(hits) -> list[str]:
    return [hit.ref for hit in hits]


# --- the sanitizer ------------------------------------------------------------


def test_a_plain_query_becomes_quoted_terms_with_a_prefix_on_the_last():
    assert to_match_query("ronaldo") == '"ronaldo"*'
    assert to_match_query("renew the domain") == '"renew" "the" "domain"*'


def test_fts5_syntax_arrives_as_ordinary_words():
    """None of this may reach FTS5 as syntax."""
    assert to_match_query("cat AND dog") == '"cat" "AND" "dog"*'
    assert to_match_query("cat NOT dog") == '"cat" "NOT" "dog"*'
    assert to_match_query("title:cat") == '"title" "cat"*'
    assert to_match_query("cat NEAR/3 dog") == '"cat" "NEAR" "3" "dog"*'
    assert to_match_query("^cat*") == '"cat"*'


def test_quotes_cannot_escape_their_own_term():
    """The security property: a token is letters and digits, so nothing inside
    one can close the quote that wraps it."""
    for nasty in ['"', '""', 'a" OR "b', '"; DROP TABLE search_index; --', 'a"*"b']:
        built = to_match_query(nasty)
        if built is None:
            continue
        # Quotes only ever appear as the wrapper: an even count, and never two
        # in a row inside a term.
        assert built.count('"') % 2 == 0
        for term in built.split():
            assert term.strip("*").startswith('"')
            assert term.strip("*").endswith('"')
            assert '"' not in term.strip("*")[1:-1]


def test_hyphens_and_punctuation_split_rather_than_negate():
    # A leading "-" is FTS5's column filter syntax in some dialects and simply
    # invalid in others; either way it must not survive.
    assert to_match_query("re-index") == '"re" "index"*'
    assert to_match_query("-ronaldo") == '"ronaldo"*'
    assert to_match_query("e.g. thing") == '"e" "g" "thing"*'


def test_nothing_searchable_returns_none():
    assert to_match_query("") is None
    assert to_match_query("   ") is None
    assert to_match_query("!!! ??? ***") is None
    assert to_match_query("—") is None


def test_cyrillic_tokenizes_like_anything_else():
    assert to_match_query("фифа ойнадым") == '"фифа" "ойнадым"*'


def test_a_pasted_paragraph_is_capped():
    built = to_match_query(" ".join(f"word{i}" for i in range(60)))
    assert len(built.split()) == svc.MAX_TERMS


# --- the index stays in sync --------------------------------------------------


def test_creating_a_task_makes_it_findable(client, auth, db):
    tasks_svc.create_task(db, TaskCreate(title="Renew the domain", notes="ronaldo reminded me"))

    found = svc.search(db, "ronaldo")
    assert [hit.title for hit in found.tasks] == ["Renew the domain"]
    assert found.total == 1


def test_editing_a_task_reindexes_it(client, auth, db):
    task = tasks_svc.create_task(db, TaskCreate(title="Buy milk"))
    assert svc.search(db, "milk").total == 1

    tasks_svc.update_task(db, task, TaskUpdate(title="Buy bread"))

    assert svc.search(db, "milk").total == 0
    assert svc.search(db, "bread").total == 1


def test_deleting_a_task_removes_it_from_the_index(client, auth, db):
    task = tasks_svc.create_task(db, TaskCreate(title="Temporary thing"))
    assert svc.search(db, "temporary").total == 1

    tasks_svc.delete_task(db, task)
    assert svc.search(db, "temporary").total == 0


def test_every_kind_lands_in_its_own_group(client, auth, db):
    articles_svc.create_article(
        db,
        ArticleCreate(
            slug="on-focus",
            title="On focus",
            description="A note about zharyq",
            date="2026-08-01",
            read_time="3 min",
            body=[],
            body_md="zharyq is the word",
        ),
    )
    diary_svc.upsert_entry(db, "2026-08-09", "zharyq of a day", title="Wednesday")
    tasks_svc.create_task(db, TaskCreate(title="think about zharyq"))
    # Through the service, never the router: the router mirrors into his real
    # Google Calendar.
    calendar_svc.create_event(
        db, CalendarEventCreate(title="zharyq review", starts_at="2026-08-10T09:00:00")
    )
    inbox_svc.create_item(db, "zharyq, whatever that means")

    found = svc.search(db, "zharyq")

    assert refs(found.articles) == ["on-focus"]
    assert refs(found.diary) == ["2026-08-09"]
    assert len(found.tasks) == 1
    assert len(found.events) == 1
    assert len(found.inbox) == 1
    assert found.total == 5


def test_a_diary_entry_rewritten_the_same_day_is_not_duplicated(client, auth, db):
    diary_svc.upsert_entry(db, "2026-08-09", "first draft about ronaldo")
    diary_svc.upsert_entry(db, "2026-08-09", "second draft about ronaldo")

    found = svc.search(db, "ronaldo")
    assert refs(found.diary) == ["2026-08-09"]
    assert "second" in found.diary[0].snippet


def test_the_hit_carries_the_date_the_thing_is_about(client, auth, db):
    diary_svc.upsert_entry(db, "2026-08-09", "a day with ronaldo in it")
    calendar_svc.create_event(
        db, CalendarEventCreate(title="ronaldo match", starts_at="2026-08-10T21:00:00")
    )

    found = svc.search(db, "ronaldo")
    assert found.diary[0].date == "2026-08-09"
    assert found.events[0].date == "2026-08-10"  # trimmed off the offset


# --- building the index from rows that already exist --------------------------


def test_rebuilding_indexes_rows_written_while_the_index_was_gone(client, auth, db):
    """The migration case: his diary and tasks predate the index."""
    tasks_svc.create_task(db, TaskCreate(title="written before search existed"))

    drop_search_index(engine)
    assert svc.search(db, "before").total == 0  # no index — empty, not a 500

    ensure_search_index(engine)
    assert svc.search(db, "before").total == 1


def test_reindex_counts_what_it_indexed(client, auth, db):
    tasks_svc.create_task(db, TaskCreate(title="one"))
    diary_svc.upsert_entry(db, "2026-08-09", "two")

    assert rebuild_search_index(engine) == 2


def test_ensure_is_idempotent_and_does_not_double_index(client, auth, db):
    tasks_svc.create_task(db, TaskCreate(title="ronaldo"))

    ensure_search_index(engine)
    ensure_search_index(engine)

    assert len(svc.search(db, "ronaldo").tasks) == 1


# --- ranking and snippets -----------------------------------------------------


def test_a_title_match_outranks_a_body_only_match(client, auth, db):
    tasks_svc.create_task(db, TaskCreate(title="Something else", notes="ronaldo in the notes"))
    tasks_svc.create_task(db, TaskCreate(title="Ronaldo", notes="nothing relevant"))

    found = svc.search(db, "ronaldo")
    assert [hit.title for hit in found.tasks] == ["Ronaldo", "Something else"]


def test_all_terms_must_match(client, auth, db):
    tasks_svc.create_task(db, TaskCreate(title="ronaldo and messi"))
    tasks_svc.create_task(db, TaskCreate(title="ronaldo alone"))

    assert len(svc.search(db, "ronaldo messi").tasks) == 1


def test_the_last_term_matches_as_a_prefix(client, auth, db):
    tasks_svc.create_task(db, TaskCreate(title="ronaldo"))

    assert len(svc.search(db, "ron").tasks) == 1
    assert len(svc.search(db, "onald").tasks) == 0  # a prefix, not a substring


def test_the_snippet_marks_the_match_and_drops_markdown_noise(client, auth, db):
    diary_svc.upsert_entry(db, "2026-08-09", "## Бүгін фифа көп ойнап қойдым.")

    hit = svc.search(db, "фифа").diary[0]
    assert f"{MARK_START}фифа{MARK_END}" in hit.snippet
    assert "#" not in hit.snippet


def test_a_hit_with_no_body_still_gets_a_snippet(client, auth, db):
    tasks_svc.create_task(db, TaskCreate(title="Ronaldo"))

    hit = svc.search(db, "ronaldo").tasks[0]
    assert hit.snippet == f"{MARK_START}Ronaldo{MARK_END}"


def test_the_limit_is_per_group(client, auth, db):
    for i in range(8):
        tasks_svc.create_task(db, TaskCreate(title=f"ronaldo {i}"))

    assert len(svc.search(db, "ronaldo", limit=3).tasks) == 3


# --- the endpoint -------------------------------------------------------------


def test_search_is_admin_only(client, db):
    assert client.get("/api/search?q=ronaldo").status_code == 401
    assert client.post("/api/search/reindex").status_code == 401


def test_the_endpoint_returns_every_group_even_when_empty(client, auth, db):
    body = client.get("/api/search?q=nothingmatchesthis", headers=auth).json()

    assert body["total"] == 0
    assert body["query"] == "nothingmatchesthis"
    for group in ("articles", "diary", "tasks", "events", "inbox"):
        assert body[group] == []


def test_a_short_query_searches_for_nothing(client, auth, db):
    tasks_svc.create_task(db, TaskCreate(title="ronaldo"))

    assert client.get("/api/search?q=r", headers=auth).json()["total"] == 0
    assert client.get("/api/search?q=", headers=auth).json()["total"] == 0
    assert client.get("/api/search", headers=auth).json()["total"] == 0


@pytest.mark.parametrize(
    "nasty",
    [
        '"',
        '""""',
        'a" OR "b',
        "'; DROP TABLE search_index; --",
        "* * *",
        "^^^",
        "NEAR/",
        "col:val",
        "(unbalanced",
        "a AND (b OR c)",
        "-- comment",
        "\\",
        "%_%",
        "🙂🙂",
        "\x00null",
        "a" * 5000,
    ],
)
def test_nasty_input_never_500s(client, auth, db, nasty):
    res = client.get("/api/search", params={"q": nasty}, headers=auth)
    assert res.status_code == 200, res.text
    assert isinstance(res.json()["total"], int)


def test_the_index_survives_a_nasty_query(client, auth, db):
    """The injection tests would pass on a table that had been dropped."""
    tasks_svc.create_task(db, TaskCreate(title="ronaldo"))

    client.get("/api/search", params={"q": "'; DROP TABLE search_index; --"}, headers=auth)

    assert client.get("/api/search?q=ronaldo", headers=auth).json()["total"] == 1
    with engine.begin() as conn:
        from sqlalchemy import text as sql

        assert conn.execute(sql(f"SELECT count(*) FROM {TABLE}")).scalar_one() == 1


def test_reindex_works_over_http(client, auth, db):
    tasks_svc.create_task(db, TaskCreate(title="ronaldo"))

    assert client.post("/api/search/reindex", headers=auth).json() == {"indexed": 1}
