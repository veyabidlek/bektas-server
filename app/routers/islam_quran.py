"""Khatms, the reading log and sura notes.

Admin-only, every route. This is the diary's posture, not the reading list's:
there is no public view of how his khatm is going.
"""

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.schemas.islam import (
    KhatmCreate,
    KhatmListOut,
    KhatmOut,
    KhatmUpdate,
    QuranLogCreate,
    QuranLogEntryOut,
    QuranLogListOut,
    SuraNoteIn,
    SuraNoteListOut,
    SuraNoteOut,
)
from app.services import islam_log as log_svc
from app.services import islam_quran as svc
from app.services import islam_sura as sura_svc

router = APIRouter(prefix="/api/islam", tags=["islam"])


def _khatm_or_404(db: Session, khatm_id: str):
    khatm = svc.get_khatm(db, khatm_id)
    if not khatm:
        raise HTTPException(status_code=404, detail="Khatm not found")
    return khatm


# --- khatms ---------------------------------------------------------------


@router.get("/khatms", response_model=KhatmListOut)
def list_khatms(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    return KhatmListOut(items=svc.list_khatms(db))


@router.post("/khatms", response_model=KhatmOut, status_code=201)
def create_khatm(
    data: KhatmCreate, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    return svc.out(db, svc.create_khatm(db, data))


@router.patch("/khatms/{khatm_id}", response_model=KhatmOut)
def update_khatm(
    khatm_id: str,
    data: KhatmUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    khatm = _khatm_or_404(db, khatm_id)
    return svc.out(db, svc.update_khatm(db, khatm, data))


@router.delete("/khatms/{khatm_id}", status_code=204)
def delete_khatm(
    khatm_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    svc.delete_khatm(db, _khatm_or_404(db, khatm_id))


# --- the reading log ------------------------------------------------------


@router.get("/quran-log", response_model=QuranLogListOut)
def list_quran_log(
    khatm: str | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Newest date first. `?khatm=<id>` narrows it to one khatm."""
    return QuranLogListOut(items=log_svc.list_entries(db, khatm))


@router.post("/quran-log", response_model=QuranLogEntryOut, status_code=201)
def add_quran_log_entry(
    data: QuranLogCreate, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    """The page range is validated by the schema (1 ≤ from ≤ to ≤ 604); the one
    thing it cannot check is that the khatm exists."""
    _khatm_or_404(db, data.khatm_id)
    return log_svc.out(log_svc.add_entry(db, data))


@router.delete("/quran-log/{entry_id}", status_code=204)
def delete_quran_log_entry(
    entry_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    entry = log_svc.get_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Log entry not found")
    log_svc.delete_entry(db, entry)


# --- sura notes -----------------------------------------------------------


@router.get("/sura-notes", response_model=SuraNoteListOut)
def list_sura_notes(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    return SuraNoteListOut(items=sura_svc.list_notes(db))


@router.put("/sura-notes/{surah}", response_model=SuraNoteOut)
def put_sura_note(
    data: SuraNoteIn,
    surah: int = Path(ge=sura_svc.FIRST_SURAH, le=sura_svc.LAST_SURAH),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Upsert. Out-of-range surah numbers are 422 from the path constraint."""
    return sura_svc.upsert_note(db, surah, data.body_md)


@router.delete("/sura-notes/{surah}", status_code=204)
def delete_sura_note(
    surah: int = Path(ge=sura_svc.FIRST_SURAH, le=sura_svc.LAST_SURAH),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if not sura_svc.delete_note(db, surah):
        raise HTTPException(status_code=404, detail="Sura note not found")
