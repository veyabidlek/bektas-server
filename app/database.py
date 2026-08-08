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


def drop_tables() -> None:
    Base.metadata.drop_all(bind=engine)
