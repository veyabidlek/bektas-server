"""Import a Notion "Reading List" CSV export into `reading_items`.

Run it from the repository root, inside the app container so DATABASE_URL points
at the real database:

    python -m scripts.import_reading /path/to/reading-list.csv

It is **idempotent**: a row whose title already exists is skipped (compared
stripped and case-insensitively), so re-running after Notion gains a few books
imports only the new ones. Nothing is ever updated or deleted — this brings
books in, it does not sync them.

The export's header is:

    Name,Author,Completed,Day Count,Progress,Score,Started,Type,pages

"Day Count" is read and thrown away on purpose: it is completed - started, and
a stored derived number that can disagree with its own inputs is worse than no
number. The client computes it.

Everything above `import_rows` is a pure function of strings, which is what the
tests exercise — the parsing is where a Notion export bites (a stray group
header, ⭐ with a variation selector, "TBD" in a numeric column, a UTF-8 BOM),
and none of that needs a database to test.
"""

import csv
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models.reading import ReadingItem
from app.services.calendar import ASTANA

# Notion writes ⭐️ — U+2B50 WHITE MEDIUM STAR followed by U+FE0F VARIATION
# SELECTOR-16. Counting the star alone ignores the selector, so the score is
# right whether or not the export carries it.
STAR = "⭐"

# "could not finish" is the export's wording for a shelved book; it becomes
# `abandoned` rather than being dropped, because a book put down is part of the
# reading history.
STATUS_BY_PROGRESS = {
    "not started": "not_started",
    "in progress": "in_progress",
    "completed": "completed",
    "could not finish": "abandoned",
}

# Parsed explicitly instead of with strptime("%B %d, %Y"): %B reads month names
# out of LC_TIME, and the container's locale is not something this import
# should silently depend on.
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

# The one row in the export that is not a book: Notion writes the board's group
# header into the CSV as a row carrying nothing but its name.
GROUP_HEADER_TITLE = "books"


@dataclass(frozen=True)
class ReadingRow:
    """One parsed CSV row, ready to become a ReadingItem."""

    title: str
    author: str | None
    category: str | None
    status: str
    pages: int | None
    score: int | None
    started: str | None
    completed: str | None


def clean(value: str | None) -> str:
    """A cell as text: never None, never padded.

    Notion pads plenty of titles with a trailing space ("Why We Sleep 💤 ") and
    leaves absent columns as empty strings.
    """
    return (value or "").strip()


def parse_text(value: str | None) -> str | None:
    """A cell as an optional string — blank becomes None, not ""."""
    return clean(value) or None


def parse_status(value: str | None) -> str:
    """Notion's "Progress" select as one of the four statuses.

    Anything unrecognised — including an empty cell — is `not_started`: a book
    with no progress recorded has not been started, and an import must never
    fail over a select value someone renamed.
    """
    return STATUS_BY_PROGRESS.get(clean(value).lower(), "not_started")


def parse_score(value: str | None) -> int | None:
    """Stars counted, capped at 5. "TBD" and blank are both no score."""
    stars = clean(value).count(STAR)
    if not stars:
        return None
    return min(stars, 5)


def parse_pages(value: str | None) -> int | None:
    """The page count, or None when blank or not a number."""
    raw = clean(value).replace(" ", "")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def parse_date(value: str | None) -> str | None:
    """Notion's "February 8, 2024" as ISO "2024-02-08". Blank is None.

    An unparseable date is None rather than an error: one malformed cell must
    not cost the whole import.
    """
    raw = clean(value)
    if not raw:
        return None
    try:
        month_name, rest = raw.split(" ", 1)
        day_part, year_part = rest.split(",", 1)
        month = MONTHS[month_name.strip().lower()]
        day = int(day_part.strip())
        year = int(year_part.strip())
        return datetime(year, month, day).date().isoformat()
    except (ValueError, KeyError):
        return None


def is_group_header(row: dict) -> bool:
    """True for the stray "Books" row Notion emits for the board's group.

    It is only a header when it carries nothing else — a real book actually
    called "Books" would have an author, a date or a page count, and must still
    import. "Progress" is ignored in the check because Notion fills the select
    with its default even on the header row.
    """
    if clean(row.get("Name")).lower() != GROUP_HEADER_TITLE:
        return False
    return not any(
        clean(row.get(column))
        for column in ("Author", "Completed", "Started", "Score", "Type", "pages")
    )


def parse_row(row: dict) -> ReadingRow | None:
    """One CSV row as a ReadingRow, or None when the row is not a book."""
    title = clean(row.get("Name"))
    if not title or is_group_header(row):
        return None

    return ReadingRow(
        title=title,
        author=parse_text(row.get("Author")),
        category=parse_text(row.get("Type")),
        status=parse_status(row.get("Progress")),
        pages=parse_pages(row.get("pages")),
        score=parse_score(row.get("Score")),
        started=parse_date(row.get("Started")),
        completed=parse_date(row.get("Completed")),
    )


def parse_csv(path: Path) -> list[ReadingRow]:
    """Every book in the export, in file order.

    utf-8-sig, because Notion writes a BOM and utf-8 would fold it into the
    first header name — "Name" would come back as "﻿Name" and every title
    would read as empty.
    """
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [parsed for row in csv.DictReader(handle) if (parsed := parse_row(row)) is not None]


def existing_titles(db: Session) -> set[str]:
    """Titles already on the shelf, stripped and lowercased for comparison."""
    return {
        (title or "").strip().lower()
        for (title,) in db.query(ReadingItem.title).all()
    }


def import_rows(db: Session, rows: list[ReadingRow]) -> tuple[int, int]:
    """Insert every row whose title is new. Returns (imported, skipped).

    The seen-set grows as we go, so a duplicate *inside one file* is skipped
    too — the export has a pair that differ only in case.
    """
    seen = existing_titles(db)
    now = datetime.now(timezone.utc).astimezone(ASTANA).isoformat()

    imported = 0
    skipped = 0
    for row in rows:
        key = row.title.strip().lower()
        if key in seen:
            skipped += 1
            continue
        db.add(
            ReadingItem(
                title=row.title,
                author=row.author,
                category=row.category,
                status=row.status,
                pages=row.pages,
                score=row.score,
                started=row.started,
                completed=row.completed,
                created_at=now,
            )
        )
        seen.add(key)
        imported += 1

    db.commit()
    return imported, skipped


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m scripts.import_reading <csv_path>", file=sys.stderr)
        return 2

    path = Path(argv[1])
    if not path.is_file():
        print(f"no such file: {path}", file=sys.stderr)
        return 2

    # Only this table, and only if missing — a maintenance script has no
    # business creating the rest of the schema.
    ReadingItem.__table__.create(bind=engine, checkfirst=True)

    rows = parse_csv(path)
    db = SessionLocal()
    try:
        imported, skipped = import_rows(db, rows)
        total = db.query(func.count(ReadingItem.id)).scalar()
    finally:
        db.close()

    print(f"{path.name}: {len(rows)} book rows parsed")
    print(f"imported {imported}, skipped {skipped} (already on the shelf)")
    print(f"reading_items now holds {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
