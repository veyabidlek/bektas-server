from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.schemas.reading import ReadingItemIn, ReadingItemOut, ReadingListOut
from app.services import reading as svc

# Reads are public — the reading list is a page anyone can look at, with no
# visibility column and nothing to gate. Writes are admin-only.
router = APIRouter(prefix="/api/reading", tags=["reading"])


@router.get("", response_model=ReadingListOut)
def list_reading(db: Session = Depends(get_db)):
    """Public: no auth dependency, by design."""
    return ReadingListOut(items=svc.list_reading_items(db))


@router.post("", response_model=ReadingItemOut, status_code=201)
def create_reading_item(
    data: ReadingItemIn,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    return svc.out(svc.create_reading_item(db, data))


@router.put("/{item_id}", response_model=ReadingItemOut)
def update_reading_item(
    item_id: int,
    data: ReadingItemIn,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    item = svc.get_reading_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Reading item not found")
    return svc.out(svc.update_reading_item(db, item, data))


@router.delete("/{item_id}", status_code=204)
def delete_reading_item(
    item_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    item = svc.get_reading_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Reading item not found")
    svc.delete_reading_item(db, item)
