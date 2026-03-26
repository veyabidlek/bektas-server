import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.pomodoro import PomodoroSession, Project
from app.schemas.pomodoro import SessionCreate, SessionStats


def list_projects(db: Session) -> list[Project]:
    return db.query(Project).all()


def list_sessions(
    db: Session,
    project_id: str | None = None,
    limit: int = 100,
) -> list[PomodoroSession]:
    q = db.query(PomodoroSession).order_by(PomodoroSession.started_at.desc())
    if project_id:
        q = q.filter(PomodoroSession.project_id == project_id)
    return q.limit(limit).all()


def create_session(db: Session, data: SessionCreate) -> PomodoroSession:
    session = PomodoroSession(
        id=str(uuid.uuid4())[:8],
        project_id=data.project_id,
        description=data.description,
        started_at=datetime.now(timezone.utc).isoformat(),
        duration_minutes=data.duration_minutes,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_stats(db: Session, project_id: str | None = None) -> SessionStats:
    q = db.query(PomodoroSession)
    if project_id:
        q = q.filter(PomodoroSession.project_id == project_id)

    all_sessions = q.all()

    today_str = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    month_ago = (date.today() - timedelta(days=30)).isoformat()
    year_ago = (date.today() - timedelta(days=365)).isoformat()

    today_sessions = [s for s in all_sessions if s.started_at[:10] == today_str]
    week_sessions = [s for s in all_sessions if s.started_at[:10] >= week_ago]
    month_sessions = [s for s in all_sessions if s.started_at[:10] >= month_ago]
    year_sessions = [s for s in all_sessions if s.started_at[:10] >= year_ago]

    # Daily minutes map for the past year
    daily_minutes: dict[str, int] = {}
    for s in year_sessions:
        day_key = s.started_at[:10]
        daily_minutes[day_key] = daily_minutes.get(day_key, 0) + s.duration_minutes

    return SessionStats(
        today_minutes=sum(s.duration_minutes for s in today_sessions),
        today_sessions=len(today_sessions),
        week_minutes=sum(s.duration_minutes for s in week_sessions),
        week_sessions=len(week_sessions),
        month_minutes=sum(s.duration_minutes for s in month_sessions),
        month_sessions=len(month_sessions),
        year_minutes=sum(s.duration_minutes for s in year_sessions),
        year_sessions=len(year_sessions),
        daily_minutes=daily_minutes,
    )
