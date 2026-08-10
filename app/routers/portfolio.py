from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin, viewer_level, visible_levels
from app.models.portfolio import PortfolioProject
from app.schemas.portfolio import (
    PortfolioImageOut,
    PortfolioProjectCreate,
    PortfolioProjectOut,
    PortfolioProjectUpdate,
)
from app.services import portfolio as svc
from app.services import portfolio_images as images_svc
from app.services.image_optimize import ALLOWED_CONTENT_TYPES

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("", response_model=list[PortfolioProjectOut])
def get_portfolio_projects(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    level: str = Depends(viewer_level),
):
    return svc.list_portfolio_projects(
        db, include_archived=include_archived, levels=visible_levels(level)
    )


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


# --- screenshots ----------------------------------------------------------
#
# Upload and delete are admin-only; *serving* is public, because a project card
# is public content and its `<img>` has to load for a logged-out reader.
#
# The upload takes no project id on purpose: the add-project form needs a URL
# before the project row exists. An image is therefore free-standing, and
# `screenshot_url` merely points at one — an external URL still works.


@router.post("/images", response_model=list[PortfolioImageOut], status_code=201)
async def upload_portfolio_images(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    saved: list[PortfolioImageOut] = []
    for upload in files:
        content_type = (upload.content_type or "").lower()
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=415, detail=f"Unsupported image type: {content_type or 'unknown'}"
            )

        data = await upload.read(images_svc.MAX_UPLOAD_BYTES + 1)
        if len(data) > images_svc.MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"{upload.filename} is too large")
        if not data:
            continue

        saved.append(images_svc.add_image(db, data, content_type))

    if not saved:
        raise HTTPException(status_code=422, detail="No image uploaded")
    return saved


@router.get("/images/{image_id}")
def serve_portfolio_image(image_id: str, db: Session = Depends(get_db)):
    """Serve a hosted screenshot — public, no auth dependency."""
    image = images_svc.get_image(db, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    path = images_svc.image_path(image)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file missing")

    return FileResponse(
        path,
        media_type=image.content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.delete("/images/{image_id}", status_code=204)
def delete_portfolio_image(
    image_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if not images_svc.delete_image(db, image_id):
        raise HTTPException(status_code=404, detail="Image not found")
