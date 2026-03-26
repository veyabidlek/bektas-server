"""Sync data from Supabase (prod) to local PostgreSQL (dev).

Run: python -m app.sync_from_supabase

Reads from SUPABASE_DATABASE_URL, writes to DATABASE_URL.
Drops and recreates all local tables before copying.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import Base, SessionLocal, create_tables, drop_tables, engine

load_dotenv()

SUPABASE_DATABASE_URL = os.getenv("SUPABASE_DATABASE_URL")

TABLES = [
    "articles",
    "comments",
    "habits",
    "habit_completions",
    "projects",
    "pomodoro_sessions",
    "experience_items",
    "skill_categories",
    "education_items",
]


def main():
    if not SUPABASE_DATABASE_URL:
        print("Error: SUPABASE_DATABASE_URL not set in .env")
        return

    print("Connecting to Supabase...")
    supa_engine = create_engine(SUPABASE_DATABASE_URL)
    SupaSession = sessionmaker(bind=supa_engine)
    supa_db = SupaSession()

    print("Resetting local database...")
    drop_tables()
    create_tables()

    local_db = SessionLocal()

    try:
        for table_name in TABLES:
            print(f"  Copying {table_name}...")

            rows = supa_db.execute(text(f"SELECT * FROM {table_name}")).mappings().all()

            if not rows:
                print(f"    (empty)")
                continue

            columns = list(rows[0].keys())
            placeholders = ", ".join(f":{col}" for col in columns)
            col_names = ", ".join(columns)
            insert_sql = text(f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})")

            for row in rows:
                local_db.execute(insert_sql, dict(row))

            print(f"    {len(rows)} rows")

        local_db.commit()
        print("Sync complete!")

    finally:
        supa_db.close()
        local_db.close()
        supa_engine.dispose()


if __name__ == "__main__":
    main()
