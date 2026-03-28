from sqlalchemy.orm import Session

from app.models.portfolio import PortfolioProject
from app.schemas.portfolio import PortfolioProjectCreate, PortfolioProjectOut, PortfolioProjectUpdate


def _to_out(p: PortfolioProject) -> PortfolioProjectOut:
    return PortfolioProjectOut(
        id=p.id,
        title=p.title,
        description=p.description,
        screenshot_url=p.screenshot_url,
        website_url=p.website_url,
        github_url=p.github_url,
        stack=p.stack or [],
        featured=p.featured,
        sort_order=p.sort_order,
        archived=p.archived,
    )


def list_portfolio_projects(db: Session, include_archived: bool = False) -> list[PortfolioProjectOut]:
    q = db.query(PortfolioProject)
    if not include_archived:
        q = q.filter(PortfolioProject.archived == False)  # noqa: E712
    projects = q.order_by(PortfolioProject.featured.desc(), PortfolioProject.sort_order.asc()).all()
    return [_to_out(p) for p in projects]


def create_portfolio_project(db: Session, data: PortfolioProjectCreate) -> PortfolioProjectOut:
    project = PortfolioProject(
        id=data.id,
        title=data.title,
        description=data.description,
        screenshot_url=data.screenshot_url,
        website_url=data.website_url,
        github_url=data.github_url,
        stack=data.stack,
        featured=False,
        sort_order=data.sort_order,
        archived=False,
    )
    db.add(project)
    db.commit()
    return _to_out(project)


def update_portfolio_project(db: Session, project_id: str, data: PortfolioProjectUpdate) -> PortfolioProjectOut | None:
    project = db.query(PortfolioProject).filter(PortfolioProject.id == project_id).first()
    if not project:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    return _to_out(project)


def archive_portfolio_project(db: Session, project_id: str) -> PortfolioProjectOut | None:
    project = db.query(PortfolioProject).filter(PortfolioProject.id == project_id).first()
    if not project:
        return None
    project.archived = not project.archived
    db.commit()
    return _to_out(project)


def feature_portfolio_project(db: Session, project_id: str) -> PortfolioProjectOut | None:
    project = db.query(PortfolioProject).filter(PortfolioProject.id == project_id).first()
    if not project:
        return None
    project.featured = not project.featured
    db.commit()
    return _to_out(project)
