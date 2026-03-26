"""Seed the database with mock data matching the frontend.

Run: python -m app.seed
"""

import random
from datetime import date, datetime, timedelta, timezone

from app.database import SessionLocal, create_tables, drop_tables
from app.models.about import EducationItem, ExperienceItem, SkillCategory
from app.models.article import Article, Comment
from app.models.habit import Habit, HabitCompletion
from app.models.pomodoro import PomodoroSession, Project


def seed_articles(db):
    articles = [
        {
            "slug": "building-a-personal-website-with-nextjs-16",
            "title": "Building a personal website with Next.js 16",
            "description": "A walkthrough of how I built this site from scratch using Next.js 16, Tailwind CSS v4, and shadcn/ui.",
            "date": "March 15, 2026",
            "read_time": "6 min read",
            "body": [
                "I've been meaning to rebuild my personal website for a while. The old one was a static HTML page I threw together years ago — functional, but not something I was proud of. When Next.js 16 dropped with Turbopack as the default bundler and React 19.2 support, it felt like the right time.",
                "The stack is intentionally simple: Next.js 16 with the App Router, Tailwind CSS v4 (which finally ditches the config file in favor of CSS-native @theme blocks), and shadcn/ui for the handful of interactive components I needed. No CMS, no database — just files.",
                "One thing I wanted to get right was the dark mode implementation. I went with next-themes because it handles the flash-of-unstyled-content problem elegantly. The theme provider wraps the app at the layout level, and a small toggle component in the navbar lets you switch between light, dark, and system preference.",
                "For typography, I paired Geist Sans (the body font) with Playfair Display for headings. The contrast between the geometric sans-serif and the high-contrast serif gives the site a editorial feel without being too heavy. The gold accent color adds just enough personality.",
                "The cursor particle effect was a fun addition. It's a simple canvas element that spawns small gold dots at the mouse position, each with a slight velocity and gravity. They fade out over about 40-70 frames. The whole thing runs at 60fps and adds maybe 2KB to the bundle.",
                "If you're thinking about building your own site, my advice is: start simple. You can always add complexity later. A single page with your name, a sentence about what you do, and a way to contact you is more than enough to start.",
            ],
            "comments": [
                {"id": "c1", "author": "Sarah Chen", "avatar": "SC", "date": "March 16, 2026", "body": "Love the clean aesthetic! The gold accent is a nice touch. Did you consider using CSS animations instead of Framer Motion for the entrance effects?"},
                {"id": "c2", "author": "Marcus Rivera", "avatar": "MR", "date": "March 16, 2026", "body": "Great write-up. I've been wanting to try Next.js 16 but was worried about breaking changes. This makes it seem pretty straightforward."},
                {"id": "c3", "author": "Aiko Tanaka", "avatar": "AT", "date": "March 17, 2026", "body": "The particle effect is such a subtle but delightful detail. Would love to see a standalone tutorial on just that part!"},
            ],
        },
        {
            "slug": "on-designing-with-constraints",
            "title": "On designing with constraints",
            "description": "Why limitations in design aren't obstacles — they're the thing that makes good work possible.",
            "date": "February 22, 2026",
            "read_time": "4 min read",
            "body": [
                "There's a common misconception that creativity thrives in complete freedom. Give someone a blank canvas and unlimited resources, and they'll produce their best work. In my experience, the opposite is true.",
                "Every meaningful design decision I've made has come from working within constraints. A tight deadline forces you to prioritize. A small screen forces you to distill your message. A limited color palette forces you to think about contrast and hierarchy.",
                "When I started this website, I gave myself a constraint: one accent color. Just gold. Everything else is black, white, and gray. This single rule eliminated hundreds of micro-decisions about color and let me focus on typography, spacing, and content.",
                "The best design systems I've worked with embrace this philosophy. They don't give you infinite options — they give you a curated set of tokens, components, and patterns that work well together. The constraint isn't limiting; it's liberating.",
                "Next time you're stuck on a design problem, try adding a constraint instead of removing one. You might be surprised at how much easier the solution becomes.",
            ],
            "comments": [
                {"id": "c4", "author": "Jordan Park", "avatar": "JP", "date": "February 23, 2026", "body": "This resonates so much. I've been working with a very restricted component library at work and it's actually made our product more cohesive."},
                {"id": "c5", "author": "Elena Volkov", "avatar": "EV", "date": "February 24, 2026", "body": "The one-accent-color constraint is brilliant. I might steal that for my next project."},
            ],
        },
        {
            "slug": "the-art-of-clean-code",
            "title": "The art of clean code",
            "description": "Thoughts on what makes code truly clean — and why it matters more than you think.",
            "date": "January 10, 2026",
            "read_time": "5 min read",
            "body": [
                "Clean code is not about following rules. It's about empathy. Every line you write is a message to the next person who reads it — and that person might be you, six months from now, at 2am, trying to fix a production bug.",
                "I used to think clean code meant short code. Fewer lines, more clever abstractions, compressed logic. I was wrong. Clean code is code that communicates its intent clearly. Sometimes that means more lines, not fewer.",
                "Here's what I've learned matters most: naming things well, keeping functions small and focused, and organizing code so that related things are close together. These aren't revolutionary ideas, but they're surprisingly hard to do consistently.",
                "The naming problem is the hardest. A good name eliminates the need for a comment. If you need a comment to explain what a variable holds or what a function does, the name is wrong. Rename it until the comment becomes redundant.",
                "Small functions are another underrated tool. If a function does one thing and its name describes that thing, you can read code almost like prose. You don't need to hold the entire implementation in your head — the function name tells you what happens, and you can trust it.",
                "I've also come to appreciate the value of boring code. Clever code is fun to write and painful to debug. Boring code is predictable, readable, and maintainable. In a team setting, boring code wins every time.",
            ],
            "comments": [
                {"id": "c6", "author": "David Kim", "avatar": "DK", "date": "January 11, 2026", "body": '"Every line you write is a message to the next person who reads it" — this should be printed on every developer\'s monitor.'},
                {"id": "c7", "author": "Priya Sharma", "avatar": "PS", "date": "January 12, 2026", "body": "I completely agree about boring code. I've seen too many clever one-liners that nobody could debug when they broke."},
                {"id": "c8", "author": "Tom Wright", "avatar": "TW", "date": "January 13, 2026", "body": "Great article. One thing I'd add: clean code also means clean tests. If your tests are hard to read, you've just moved the complexity somewhere else."},
                {"id": "c9", "author": "Lisa Nguyen", "avatar": "LN", "date": "January 14, 2026", "body": "The point about naming is spot on. I spend more time naming things than writing the actual logic, and I think that's the right trade-off."},
            ],
        },
    ]

    for a in articles:
        comments_data = a.pop("comments")
        article = Article(**a)
        db.add(article)
        for c in comments_data:
            db.add(Comment(**c, article_slug=a["slug"]))


def seed_habits(db):
    habits_config = [
        ("exercise", "Exercise", "💪", "oklch(0.72 0.19 145)", 0.65, True),
        ("quran", "Quran Reading", "📖", "oklch(0.72 0.15 250)", 0.75, True),
        ("books", "Reading Books", "📚", "oklch(0.75 0.18 55)", 0.5, False),
    ]

    today = date.today()

    for hid, name, emoji, color, probability, streak_bias in habits_config:
        db.add(Habit(id=hid, name=name, emoji=emoji, color=color))

        was_yesterday = False
        for i in range(365, -1, -1):
            d = today - timedelta(days=i)
            p: float = probability + 0.2 if streak_bias and was_yesterday else probability
            done = random.random() < min(p, 0.95)
            if done:
                db.add(HabitCompletion(habit_id=hid, date=d.isoformat()))
            was_yesterday = done


def seed_pomodoro(db):
    projects_data = [
        ("personal-site", "Personal Website", "oklch(0.795 0.16 84)"),
        ("side-project", "Side Project", "oklch(0.72 0.19 145)"),
        ("learning", "Learning", "oklch(0.72 0.15 250)"),
        ("freelance", "Freelance Work", "oklch(0.75 0.18 25)"),
    ]
    for pid, name, color in projects_data:
        db.add(Project(id=pid, name=name, color=color))

    tasks = [
        ("personal-site", ["Hero section redesign", "About page layout", "Dark mode fixes", "Writing page comments", "CSS animations"]),
        ("side-project", ["API endpoint design", "Database schema", "Auth flow", "Testing setup"]),
        ("learning", ["TypeScript generics", "React Server Components", "Next.js 16 docs", "Tailwind v4 migration"]),
        ("freelance", ["Client meeting prep", "Landing page mockup", "Invoice dashboard", "Email templates"]),
    ]

    sid = 1
    today = datetime.now(timezone.utc)

    # Today's sessions
    for desc, hour in [
        ("Pomodoro page implementation", 9),
        ("Habit tracker grid", 9),
        ("Next.js 16 docs", 10),
        ("Writing page styling", 11),
    ]:
        pid = "personal-site" if "Next.js" not in desc else "learning"
        t = today.replace(hour=hour, minute=random.randint(0, 30), second=0, microsecond=0)
        db.add(PomodoroSession(
            id=f"s{sid}", project_id=pid, description=desc,
            started_at=t.isoformat(), duration_minutes=25,
        ))
        sid += 1

    # Past 364 days
    for day in range(1, 365):
        d = today - timedelta(days=day)
        is_weekend = d.weekday() >= 5
        if random.random() > (0.35 if is_weekend else 0.75):
            continue

        count = random.randint(1, 3) if is_weekend else random.randint(2, 7)
        hour = 8 + random.randint(0, 1)

        for _ in range(count):
            project_id, descs = random.choice(tasks)
            desc = random.choice(descs)
            duration = 25 if random.random() > 0.2 else 50
            t = d.replace(hour=hour, minute=random.randint(0, 50), second=0, microsecond=0)
            db.add(PomodoroSession(
                id=f"s{sid}", project_id=project_id, description=desc,
                started_at=t.isoformat(), duration_minutes=duration,
            ))
            sid += 1
            hour += 1


def seed_about(db):
    experience = [
        ExperienceItem(company="Acme Corp", role="Senior Software Engineer", period="2024 — Present", description="Leading frontend architecture for the core product. Built a design system used across 5 teams, improved Lighthouse performance score from 62 to 94.", sort_order=0),
        ExperienceItem(company="FinStack", role="Full-Stack Engineer", period="2022 — 2024", description="Developed real-time payment processing dashboard serving 10k+ daily active users. Implemented WebSocket-based live transaction feeds and analytics.", sort_order=1),
        ExperienceItem(company="DevToolsCo", role="Frontend Engineer", period="2021 — 2022", description="Built developer-facing CLI and web dashboard for API monitoring. Reduced onboarding time by 40% through improved documentation and interactive tutorials.", sort_order=2),
        ExperienceItem(company="Freelance", role="Web Developer", period="2019 — 2021", description="Designed and developed websites and web apps for startups and small businesses. Worked across e-commerce, portfolio sites, and internal tools.", sort_order=3),
    ]
    for e in experience:
        db.add(e)

    skills = [
        SkillCategory(title="Languages", skills=["TypeScript", "JavaScript", "Python", "Go", "SQL"], sort_order=0),
        SkillCategory(title="Frontend", skills=["React", "Next.js", "Tailwind CSS", "Framer Motion", "Figma"], sort_order=1),
        SkillCategory(title="Backend", skills=["Node.js", "PostgreSQL", "Redis", "GraphQL", "REST APIs"], sort_order=2),
        SkillCategory(title="Tools & Infra", skills=["Git", "Docker", "AWS", "Vercel", "GitHub Actions"], sort_order=3),
    ]
    for s in skills:
        db.add(s)

    education = [
        EducationItem(institution="Technical University of Berlin", degree="M.Sc. Computer Science", period="2020 — 2022", note="Focus on distributed systems and human-computer interaction", sort_order=0),
        EducationItem(institution="University of Applied Sciences", degree="B.Sc. Software Engineering", period="2016 — 2020", note="Graduated with honors", sort_order=1),
    ]
    for e in education:
        db.add(e)


def main():
    print("Dropping tables...")
    drop_tables()
    print("Creating tables...")
    create_tables()

    db = SessionLocal()
    try:
        print("Seeding articles...")
        seed_articles(db)
        print("Seeding habits...")
        seed_habits(db)
        print("Seeding pomodoro...")
        seed_pomodoro(db)
        print("Seeding about...")
        seed_about(db)
        db.commit()
        print("Done! Database seeded.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
