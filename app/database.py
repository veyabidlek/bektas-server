import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("SUPABASE_DATABASE_URL") or os.getenv("DATABASE_URL", "postgresql://bektas:bektas@localhost:5432/bektas_dev")

# SQLite needs check_same_thread=False: FastAPI serves requests on a
# threadpool, and the default would reject a connection reused across
# threads. No-op for any other backend.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Columns added to tables that already existed in production. create_all() only
# creates missing *tables*, never missing columns, so new columns on old tables
# have to be added explicitly. Each entry is idempotent — checked before it runs.
_ADDED_COLUMNS: list[tuple[str, str, str]] = [
    ("habits", "visibility", "VARCHAR NOT NULL DEFAULT 'public'"),
    ("articles", "visibility", "VARCHAR NOT NULL DEFAULT 'public'"),
    ("articles", "body_md", "TEXT NOT NULL DEFAULT ''"),
    ("projects", "visibility", "VARCHAR NOT NULL DEFAULT 'public'"),
    ("portfolio_projects", "visibility", "VARCHAR NOT NULL DEFAULT 'public'"),
    # Added 2026-08-08, after Bektas had already written entries — create_all()
    # would have left the existing table untouched.
    ("diary_entries", "title", "VARCHAR NOT NULL DEFAULT ''"),
    # Set once the Telegram bot has pinged about an event, so a restart cannot
    # double-send. Added 2026-08-08 when the table already had rows.
    ("calendar_events", "reminder_fired_at", "VARCHAR"),
    # What a habit is for — "education" / "health" / "islam". Nullable with no
    # default: every habit Bektas already tracks stays ungrouped until he says
    # otherwise. Added 2026-08-10 to a table full of rows.
    ("habits", "category", "VARCHAR"),
    # "done" | "partial". Added 2026-08-10 to a table that already holds every
    # completion Bektas has ticked — the DEFAULT is what silently reclassifies
    # all of them as fully done, which is what they were.
    ("habit_completions", "state", "VARCHAR NOT NULL DEFAULT 'done'"),
    # The public Shelf view, added 2026-08-10 to a table already holding every
    # book of the Notion import. Both nullable with no default: an imported row
    # has neither a blurb nor a cover until Bektas gives it one.
    ("reading_items", "description", "TEXT"),
    ("reading_items", "cover_image", "VARCHAR"),
    # When the habit was added ("YYYY-MM-DD", Almaty). Added 2026-08-11 to a
    # table full of rows; NULL for them on purpose — their "tracked since" is
    # their earliest completion, and inventing a date here would claim the
    # grid's pre-history was really missed.
    ("habits", "created_at", "VARCHAR"),
    # Counted habits (HabitKit import, 2026-08-11): a daily goal on the habit,
    # the day's count on the completion. Both NULL everywhere they don't
    # apply — a plain habit and a state-only write carry no numbers.
    ("habits", "target_per_day", "INTEGER"),
    ("habit_completions", "amount", "INTEGER"),
]


def ensure_columns() -> None:
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, column, ddl in _ADDED_COLUMNS:
            if table not in existing_tables:
                continue  # create_all() will build it with the column already in place
            columns = {c["name"] for c in inspector.get_columns(table)}
            if column in columns:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_columns()
    # Imported here, not at module scope: search_index reads `engine` from this
    # module, and a top-level import would be a cycle.
    from app.services.search_index import ensure_search_index

    ensure_search_index(engine)


def drop_tables() -> None:
    Base.metadata.drop_all(bind=engine)
