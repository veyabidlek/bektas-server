from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.models.portfolio import PortfolioProject
from app.schemas.portfolio import PortfolioProjectCreate, PortfolioProjectOut, PortfolioProjectUpdate
from app.services import portfolio as svc

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("", response_model=list[PortfolioProjectOut])
def get_portfolio_projects(
    include_archived: bool = False,
    db: Session = Depends(get_db),
):
    return svc.list_portfolio_projects(db, include_archived=include_archived)


@router.post("", response_model=PortfolioProjectOut, status_code=201)
def create_portfolio_project(
    data: PortfolioProjectCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    existing = db.query(PortfolioProject).filter(PortfolioProject.id == data.id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Project already exists")
    return svc.create_portfolio_project(db, data)


@router.put("/{project_id}", response_model=PortfolioProjectOut)
def update_portfolio_project(
    project_id: str,
    data: PortfolioProjectUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    result = svc.update_portfolio_project(db, project_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


@router.patch("/{project_id}/archive", response_model=PortfolioProjectOut)
def archive_portfolio_project(
    project_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    result = svc.archive_portfolio_project(db, project_id)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


@router.patch("/{project_id}/feature", response_model=PortfolioProjectOut)
def feature_portfolio_project(
    project_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    result = svc.feature_portfolio_project(db, project_id)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result
