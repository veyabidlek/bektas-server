from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.about import AboutOut
from app.services import about as svc

router = APIRouter(prefix="/api/about", tags=["about"])


@router.get("", response_model=AboutOut)
def get_about(db: Session = Depends(get_db)):
    return svc.get_about(db)
