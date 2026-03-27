from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.schemas.pomodoro import ProjectOut, SessionCreate, SessionOut, SessionStats
from app.services import pomodoro as svc

router = APIRouter(tags=["pomodoro"])


@router.get("/api/projects", response_model=list[ProjectOut])
def get_projects(db: Session = Depends(get_db)):
    return svc.list_projects(db)


@router.get("/api/sessions", response_model=list[SessionOut])
def get_sessions(
    project_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return svc.list_sessions(db, project_id=project_id, limit=limit)


@router.get("/api/sessions/stats", response_model=SessionStats)
def get_session_stats(
    project_id: str | None = None,
    db: Session = Depends(get_db),
):
    return svc.get_stats(db, project_id=project_id)


@router.post("/api/sessions", response_model=SessionOut, status_code=201)
def create_session(
    data: SessionCreate,
    db: Session = Depends(get_db),
):
    return svc.create_session(db, data)


@router.delete("/api/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    svc.delete_session(db, session_id)
