"""The FTS5 index behind universal search.

One index for everything Bektas owns — writings, diary, tasks, events, inbox —
rather than five. The alternative (an external-content FTS table per model) would
mean five virtual tables, five sets of triggers and a five-way UNION at query
time to rank across them; a single table with `kind` as an UNINDEXED column gives
the same recall, one `MATCH`, and one place to change when a sixth thing becomes
searchable.

Sync is done by SQLite triggers, not by application code. Every write path that
exists today (web, the Telegram bot, a triage that turns an inbox item into a
task) and every one that does not exist yet goes through the same three
statements, so the index cannot drift because someone forgot to call it. The
price is that the mapping from a row to its indexed text lives in SQL — see the
`Source` table below, which is the whole specification.

SQLite only. The prod database is SQLite (see docker-compose.prod.yml) and so is
the test database; on any other backend this no-ops and search degrades to
"nothing found" rather than to a 500.
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

TABLE = "search_index"

# Column order matters: `snippet()` and `bm25()` address columns by position.
KIND_COL, REF_COL, DAY_COL, TITLE_COL, BODY_COL = range(5)


@dataclass(frozen=True)
class Source:
    """One searchable model, expressed as SQL over a trigger row alias.

    `title`/`body`/`day` are format strings taking `{r}` — `new` or `old` — so
    the same definition builds the insert half and the delete half of every
    trigger, and the backfill, from one place.
    """

    kind: str
    table: str
    ref: str
    day: str
    title: str
    body: str


# The `day` of a hit is whatever date the thing is *about*, not when the row was
# touched: a writing's publish date, the diary's day, an event's start. A task
# has no natural date until it is due, so it falls back to when it was captured.
SOURCES: tuple[Source, ...] = (
    Source(
        kind="article",
        table="articles",
        ref="slug",
        day="{r}.date",
        title="{r}.title",
        # Legacy rows keep their JSON block `body` and an empty `body_md`; the
        # description is indexed either way, so an old writing is still findable
        # by its summary line.
        body="coalesce({r}.description, '') || char(10) || coalesce({r}.body_md, '')",
    ),
    Source(
        kind="diary",
        table="diary_entries",
        ref="day",
        day="{r}.day",
        title="coalesce({r}.title, '')",
        body="coalesce({r}.body_md, '')",
    ),
    Source(
        kind="task",
        table="tasks",
        ref="id",
        day="coalesce({r}.due_at, {r}.created_at)",
        title="{r}.title",
        body="coalesce({r}.notes, '')",
    ),
    Source(
        kind="event",
        table="calendar_events",
        ref="id",
        day="{r}.starts_at",
        title="{r}.title",
        body="coalesce({r}.notes, '')",
    ),
    Source(
        kind="inbox",
        table="inbox_items",
        ref="id",
        day="{r}.created_at",
        # An inbox item has no title by design — capturing costs nothing. Leaving
        # the column empty keeps bm25's title weighting meaningful for the things
        # that do have one.
        title="''",
        body="coalesce({r}.text, '')",
    ),
)


def is_sqlite(engine: Engine) -> bool:
    return engine.dialect.name == "sqlite"


# `remove_diacritics 2` folds й→и and ё→е, which is what a search box should do:
# he types the word, not the spelling. Indexing and querying both fold, so the
# two always agree.
_CREATE_TABLE = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS {TABLE} USING fts5(
    kind UNINDEXED,
    ref UNINDEXED,
    day UNINDEXED,
    title,
    body,
    tokenize = 'unicode61 remove_diacritics 2'
)
"""


def _values(source: Source, alias: str) -> str:
    return (
        f"'{source.kind}', {alias}.{source.ref}, "
        f"{source.day.format(r=alias)}, "
        f"{source.title.format(r=alias)}, "
        f"{source.body.format(r=alias)}"
    )


def _insert(source: Source, alias: str) -> str:
    return f"INSERT INTO {TABLE}(kind, ref, day, title, body) VALUES ({_values(source, alias)});"


def _delete(source: Source, alias: str) -> str:
    return f"DELETE FROM {TABLE} WHERE kind = '{source.kind}' AND ref = {alias}.{source.ref};"


def _triggers(source: Source) -> list[str]:
    """Insert / update / delete, for one source table.

    The update trigger deletes by `old` and re-inserts from `new` — that is what
    keeps a renamed writing (the slug *is* the key) from leaving a ghost row.
    """
    name = f"{TABLE}_{source.kind}"
    return [
        f"CREATE TRIGGER IF NOT EXISTS {name}_ai AFTER INSERT ON {source.table} BEGIN "
        f"{_insert(source, 'new')} END",
        f"CREATE TRIGGER IF NOT EXISTS {name}_au AFTER UPDATE ON {source.table} BEGIN "
        f"{_delete(source, 'old')} {_insert(source, 'new')} END",
        f"CREATE TRIGGER IF NOT EXISTS {name}_ad AFTER DELETE ON {source.table} BEGIN "
        f"{_delete(source, 'old')} END",
    ]


def _backfill(source: Source) -> str:
    return (
        f"INSERT INTO {TABLE}(kind, ref, day, title, body) "
        f"SELECT {_values(source, source.table)} FROM {source.table}"
    )


def ensure_search_index(engine: Engine) -> bool:
    """Create the index and its triggers, and populate it from rows that already
    exist. Idempotent — safe on every startup.

    The backfill is the migration: when this first runs in production the diary,
    tasks and inbox already hold his real writing, and an index that only caught
    *future* edits would leave all of it unfindable until he happened to touch it.

    Returns True when the index was built here (first run), False when it was
    already in place.
    """
    if not is_sqlite(engine):
        return False

    with engine.begin() as conn:
        existed = conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :n"),
            {"n": TABLE},
        ).first()

        conn.execute(text(_CREATE_TABLE))

        tables = {
            row[0]
            for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))
        }

        for source in SOURCES:
            if source.table not in tables:
                continue  # not created yet — create_all() runs before this
            for trigger in _triggers(source):
                conn.execute(text(trigger))
            if not existed:
                conn.execute(text(_backfill(source)))

    return not existed


def rebuild_search_index(engine: Engine) -> int:
    """Throw the index away and build it again from the source tables.

    The escape hatch for the one thing triggers cannot cover: a write that
    bypassed them entirely (a restored backup, a hand-edited row). Returns the
    number of indexed rows.
    """
    if not is_sqlite(engine):
        return 0

    drop_search_index(engine)
    ensure_search_index(engine)

    with engine.begin() as conn:
        return conn.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar_one()


def drop_search_index(engine: Engine) -> None:
    """Remove the index and every trigger feeding it."""
    if not is_sqlite(engine):
        return

    with engine.begin() as conn:
        for source in SOURCES:
            name = f"{TABLE}_{source.kind}"
            for suffix in ("ai", "au", "ad"):
                conn.execute(text(f"DROP TRIGGER IF EXISTS {name}_{suffix}"))
        conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
