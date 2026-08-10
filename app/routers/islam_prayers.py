"""The prayer grid — admin-only, like the rest of the section."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.models.islam import PRAYERS
from app.schemas.islam import PrayerDayOut, PrayerMarkIn, PrayerRangeOut
from app.services import islam_prayers as svc

router = APIRouter(prefix="/api/islam", tags=["islam"])


def _valid_date(day: str) -> str:
    if not svc.is_valid_date(day):
        raise HTTPException(status_code=422, detail="Date must be YYYY-MM-DD")
    return day


@router.get("/prayers", response_model=PrayerRangeOut)
def list_prayer_days(
    from_: str = Query(alias="from"),
    to: str = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Every day in the range, untouched ones as `entries: {}`.

    The client draws a calendar off this, so a missing day would shift every
    cell after it. Capped at a year and a leap day: a typo'd `from` must not
    ask the server to walk the epoch one day at a time.
    """
    start, end = _valid_date(from_), _valid_date(to)
    if svc.range_length(start, end) < 1:
        raise HTTPException(status_code=422, detail="`to` must not be before `from`")
    if svc.range_length(start, end) > svc.MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=422, detail=f"Range is capped at {svc.MAX_RANGE_DAYS} days"
        )
    return PrayerRangeOut(days=svc.list_days(db, start, end))


@router.put("/prayers/{date}/{prayer}", response_model=PrayerDayOut)
def set_prayer_mark(
    date: str,
    prayer: str,
    data: PrayerMarkIn,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Upsert one cell and answer with the whole day.

    Sending both fields as null **clears** the cell — that is how a mis-tapped
    prayer goes back to "not filled in", which is a different thing from
    "skipped" and has to stay reachable.
    """
    if prayer not in PRAYERS:
        raise HTTPException(
            status_code=422, detail=f"prayer must be one of {', '.join(PRAYERS)}"
        )
    return svc.set_mark(db, _valid_date(date), prayer, data)
