from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin, require_ingest_token
from app.schemas.sleep import SleepIngestIn, SleepIngestOut, SleepListOut
from app.services import sleep as svc

# Two callers, two credentials. The POST is a machine — an Apple Shortcut
# running unattended every morning — and carries the static
# HEALTH_INGEST_TOKEN. The GET is him, logged in, and carries the admin
# session: how he slept is as private as his diary.
router = APIRouter(prefix="/api/health", tags=["health"])


@router.post("/sleep", response_model=SleepIngestOut)
def ingest_sleep(
    data: SleepIngestIn,
    db: Session = Depends(get_db),
    _: None = Depends(require_ingest_token),
):
    """Upload a night of Apple Health sleep samples.

    Answers with the night as it was stored, so the shortcut's own log shows
    what the server made of it, plus every stage name that was not recognized.
    """
    try:
        night, unrecognized = svc.ingest(db, data)
    except ValueError as exc:
        # The shortcut has no console. The message names the offending value.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if night is None:
        raise HTTPException(status_code=422, detail="No usable sleep segments in this upload")

    return SleepIngestOut(**night.model_dump(), unrecognized_stages=unrecognized)


@router.get("/sleep", response_model=SleepListOut)
def list_sleep(
    days: int = Query(default=svc.DEFAULT_DAYS, ge=1, le=svc.MAX_DAYS),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """The most recent nights, newest first. Admin-only."""
    return SleepListOut(nights=svc.list_nights(db, days))
