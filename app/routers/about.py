from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.schemas.about import AboutOut, AboutUpdate, ProfileOut, ProfileUpdate
from app.services import about as svc

router = APIRouter(prefix="/api", tags=["about"])


@router.get("/about", response_model=AboutOut)
def get_about(db: Session = Depends(get_db)):
    return svc.get_about(db)


@router.put("/about", response_model=AboutOut)
def update_about(
    data: AboutUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    return svc.update_about(db, data)


@router.get("/profile", response_model=ProfileOut)
def get_profile(db: Session = Depends(get_db)):
    return svc.get_profile(db)


@router.put("/profile", response_model=ProfileOut)
def update_profile(
    data: ProfileUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    return svc.update_profile(db, data)
