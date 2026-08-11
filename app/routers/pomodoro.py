from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin, viewer_level, visible_levels
from app.schemas.pomodoro import ProjectOut, SessionCreate, SessionOut, SessionStats
from app.services import pomodoro as svc

router = APIRouter(tags=["pomodoro"])


@router.get("/api/projects", response_model=list[ProjectOut])
def get_projects(
    db: Session = Depends(get_db),
    level: str = Depends(viewer_level),
):
    return svc.list_projects(db, levels=visible_levels(level))


class VisibilityUpdate(BaseModel):
    visibility: str


@router.patch("/api/projects/{project_id}/visibility", response_model=ProjectOut)
def set_project_visibility(
    project_id: str,
    data: VisibilityUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if data.visibility not in ("public", "friends", "private"):
        raise HTTPException(status_code=422, detail="Invalid visibility")
    project = svc.set_project_visibility(db, project_id, data.visibility)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/api/sessions", response_model=list[SessionOut])
def get_sessions(
    project_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    level: str = Depends(viewer_level),
):
    return svc.list_sessions(
        db, project_id=project_id, limit=limit, levels=visible_levels(level)
    )


@router.get("/api/sessions/stats", response_model=SessionStats)
def get_session_stats(
    project_id: str | None = None,
    db: Session = Depends(get_db),
    level: str = Depends(viewer_level),
):
    return svc.get_stats(db, project_id=project_id, levels=visible_levels(level))


@router.post("/api/sessions", response_model=SessionOut, status_code=201)
# Admin-only: sessions are Bektas's own log, not public submissions.
def create_session(
    data: SessionCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    return svc.create_session(db, data)


@router.delete("/api/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    svc.delete_session(db, session_id)
