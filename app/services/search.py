"""Universal search: one query, every thing he owns.

Two jobs live here. Turning whatever he typed into an expression FTS5 will
accept — see `to_match_query`, which is the security boundary — and running it
per kind so each group is ranked on its own merits.
"""

import re

from sqlalchemy import text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from app.schemas.search import SearchHit, SearchResults
from app.services.search_index import BODY_COL, TABLE, TITLE_COL

# Below this a query matches half the database and the panel flickers through
# nonsense on the way to a real word.
MIN_QUERY_CHARS = 2

# Sentinels around a match inside a snippet. Private-use codepoints, not markup:
# the client splits on them and renders real <mark> elements, so a diary entry
# containing "<script>" is highlighted, never executed.
MARK_START = ""
MARK_END = ""

# A token is a run of letters and digits — Unicode-aware, so Kazakh and Russian
# words tokenize exactly like English ones.
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

# Enough for any real query; a paragraph pasted into the box should not become a
# 400-term MATCH expression.
MAX_TERMS = 12

_SNIPPET_TOKENS = 14

# Markdown punctuation that survives into a snippet as noise ("## Бүгін…").
# Stripped for display only — the tokenizer already ignores it when matching.
_MD_NOISE_RE = re.compile(r"[#*_`>~\[\]]|!\[|\]\([^)]*\)")


def to_match_query(q: str) -> str | None:
    """Whatever he typed → an FTS5 MATCH expression, or None if there is nothing
    to search for.

    Everything that is not a letter or a digit is dropped, and each surviving
    token is wrapped in double quotes. That is what makes this safe: a quote
    cannot appear *inside* a token by construction, so there is no input that can
    close the quote early and have the rest read as syntax. `AND`, `NOT`, `NEAR`,
    `*`, `^`, `:` and a lone `"` all arrive as ordinary words or vanish.

    The last token gets a `*` so results appear while he is still typing it —
    "ron" already finds "ronaldo".
    """
    tokens = _TOKEN_RE.findall(q or "")[:MAX_TERMS]
    if not tokens:
        return None

    terms = [f'"{token}"' for token in tokens]
    terms[-1] += "*"
    return " ".join(terms)  # space is FTS5's implicit AND


def _clean(snippet: str) -> str:
    """Take the markdown noise off a snippet without disturbing the sentinels."""
    return " ".join(_MD_NOISE_RE.sub("", snippet).split())


def _query(kind: str) -> str:
    # bm25 takes one weight per column, in declaration order. The two UNINDEXED
    # columns can never match, so their weights are formalities; a hit in the
    # title counts for several in the body, because a task called "ronaldo" is
    # more what he meant than one that mentions him in a note.
    return f"""
        SELECT ref,
               day,
               title,
               snippet({TABLE}, {BODY_COL}, :open, :close, '…', {_SNIPPET_TOKENS}) AS body_snippet,
               snippet({TABLE}, {TITLE_COL}, :open, :close, '…', {_SNIPPET_TOKENS}) AS title_snippet
        FROM {TABLE}
        WHERE {TABLE} MATCH :match AND kind = :kind
        ORDER BY bm25({TABLE}, 0.0, 0.0, 0.0, 8.0, 1.0)
        LIMIT :limit
    """


def _hits(db: Session, kind: str, match: str, limit: int) -> list[SearchHit]:
    params = {
        "match": match,
        "kind": kind,
        "limit": limit,
        "open": MARK_START,
        "close": MARK_END,
    }
    try:
        rows = db.execute(text(_query(kind)), params).all()
    except DatabaseError:
        # A missing index (non-SQLite backend, or a database restored without
        # it) must read as "no results", never as a 500 on his search box.
        db.rollback()
        return []

    hits = []
    for ref, day, title, body_snippet, title_snippet in rows:
        # Prefer the body: it is where the surrounding sentence lives. A hit with
        # no body at all — a bare task title — falls back to the title snippet so
        # the row is never blank.
        snippet = _clean(body_snippet) or _clean(title_snippet)
        hits.append(
            SearchHit(
                kind=kind,
                ref=str(ref),
                title=(title or "").strip(),
                snippet=snippet,
                date=(day or "")[:10],
            )
        )
    return hits


def search(db: Session, q: str, limit: int = 6) -> SearchResults:
    """Search everything, grouped by kind and ranked within each group."""
    query = (q or "").strip()
    empty = SearchResults(query=query, total=0)

    if len(query) < MIN_QUERY_CHARS:
        return empty

    match = to_match_query(query)
    if not match:
        return empty  # punctuation only — nothing to look for

    groups = {
        "articles": _hits(db, "article", match, limit),
        "diary": _hits(db, "diary", match, limit),
        "tasks": _hits(db, "task", match, limit),
        "events": _hits(db, "event", match, limit),
        "inbox": _hits(db, "inbox", match, limit),
    }

    return SearchResults(
        query=query,
        total=sum(len(hits) for hits in groups.values()),
        **groups,
    )
