"""Seed Supabase database with the same mock data.

Run: python -m app.seed_supabase

Uses SUPABASE_DATABASE_URL from .env.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_DATABASE_URL")


def main():
    if not SUPABASE_URL or "YOUR_PASSWORD" in SUPABASE_URL:
        print("Error: Set your real password in SUPABASE_DATABASE_URL in .env")
        return

    print(f"Connecting to Supabase...")

    # Temporarily override the engine to point at Supabase
    supa_engine = create_engine(SUPABASE_URL)

    # Import after engine creation so models use Base
    from app.database import Base
    from app.models import (  # noqa: F401 — ensure all models registered
        Article, Comment, Habit, HabitCompletion,
        Project, PomodoroSession,
        ExperienceItem, SkillCategory, EducationItem,
        Profile,
    )

    print("Dropping existing tables...")
    Base.metadata.drop_all(bind=supa_engine)

    print("Creating tables...")
    Base.metadata.create_all(bind=supa_engine)

    SupaSession = sessionmaker(bind=supa_engine)
    db = SupaSession()

    try:
        # Reuse the same seed functions from app.seed
        from app.seed import seed_articles, seed_habits, seed_pomodoro, seed_about

        print("Seeding articles...")
        seed_articles(db)
        print("Seeding habits...")
        seed_habits(db)
        print("Seeding pomodoro...")
        seed_pomodoro(db)
        print("Seeding about...")
        seed_about(db)
        db.commit()
        print("Done! Supabase database seeded.")
    finally:
        db.close()
        supa_engine.dispose()


if __name__ == "__main__":
    main()
