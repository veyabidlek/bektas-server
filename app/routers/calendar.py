from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.schemas.calendar import (
    CalendarEventCreate,
    CalendarEventOut,
    CalendarEventUpdate,
    GoogleStatus,
)
from app.schemas.review import (
    DayScoreOut,
    EventOutcomeOut,
    OutcomeIn,
    ReviewSettings,
    ReviewSummary,
)
from app.services import calendar as svc
from app.services import gcal
from app.services import review as review_svc
from app.services.calendar import ASTANA

# Every route here is admin-only: the calendar is Bektas's own, and unlike the
# rest of the site there is no public tier to fall back to.
router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("/events", response_model=list[CalendarEventOut])
def list_events(
    start: str | None = None,
    end: str | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    return svc.list_events(db, start=start, end=end)


@router.post("/events", response_model=CalendarEventOut, status_code=201)
def create_event(
    data: CalendarEventCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if not data.title.strip():
        raise HTTPException(status_code=422, detail="Title is required")
    try:
        event = svc.create_event(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    gcal.push_event(db, event)
    return svc.out(event)


@router.put("/events/{event_id}", response_model=CalendarEventOut)
def update_event(
    event_id: str,
    data: CalendarEventUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    event = svc.get_event(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    try:
        event = svc.update_event(db, event, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    gcal.push_event(db, event)
    return svc.out(event)


@router.delete("/events/{event_id}", status_code=204)
def delete_event(
    event_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    event = svc.get_event(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    google_id = event.google_event_id
    svc.delete_event(db, event)
    # A deleted event must not keep scoring days it is no longer part of.
    review_svc.delete_outcome(db, event_id)
    gcal.remove_event(db, google_id)


# --- Evening review ---
#
# Declared before the Google block only for reading order; the important
# ordering is inside: /review/settings and /review/summary come before
# /review/{day}, or "settings" would be read as a date.


@router.get("/review/settings", response_model=ReviewSettings)
def review_settings(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    return ReviewSettings(review_time=review_svc.get_review_time(db))


@router.put("/review/settings", response_model=ReviewSettings)
def update_review_settings(
    data: ReviewSettings,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    try:
        return ReviewSettings(review_time=review_svc.set_review_time(db, data.review_time))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/review/summary", response_model=ReviewSummary)
def review_summary(
    days: int = 7,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Yesterday, today so far, and the strip — one request for the dashboard."""
    span = max(1, min(days, 31))
    today = datetime.now(ASTANA).strftime("%Y-%m-%d")
    window = [
        (datetime.fromisoformat(today) - timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(span - 1, -1, -1)
    ]
    scores = [DayScoreOut(**vars(s)) for s in review_svc.day_scores(db, window)]
    yesterday = (datetime.fromisoformat(today) - timedelta(days=1)).strftime("%Y-%m-%d")

    return ReviewSummary(
        today=DayScoreOut(**vars(review_svc.day_score(db, today))),
        yesterday=DayScoreOut(**vars(review_svc.day_score(db, yesterday))),
        days=scores,
    )


@router.get("/review/{day}", response_model=DayScoreOut)
def review_day(day: str, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    return DayScoreOut(**vars(review_svc.day_score(db, day)))


@router.put("/events/{event_id}/outcome", response_model=EventOutcomeOut)
def set_outcome(
    event_id: str,
    data: OutcomeIn,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Answer for one event. Re-answering overwrites — same as tapping again in chat."""
    if not svc.get_event(db, event_id):
        raise HTTPException(status_code=404, detail="Event not found")
    try:
        row = review_svc.record_outcome(db, event_id, data.outcome, data.note)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return EventOutcomeOut(
        event_id=row.event_id,
        outcome=row.outcome,
        note=row.note,
        recorded_at=row.recorded_at,
    )


# --- Google Calendar ---


@router.get("/google/status", response_model=GoogleStatus)
def google_status(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    return GoogleStatus(**gcal.status(db))


@router.post("/google/auth-url")
def google_auth_url(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    try:
        return {"url": gcal.build_auth_url(db)}
    except gcal.GoogleNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/google/callback")
def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """Where Google sends the browser back.

    Deliberately unauthenticated: it is a top-level redirect from Google, so no
    Authorization header rides along. The one-time `state` written when the
    admin asked for the URL is what proves the request is his.
    """
    target = "/bekonai-admin/calendar"

    if error or not code or not state:
        return RedirectResponse(f"{target}?google=error", status_code=303)

    try:
        gcal.complete_auth(db, code, state)
    except (gcal.GoogleError, gcal.GoogleNotConfigured):
        return RedirectResponse(f"{target}?google=error", status_code=303)

    return RedirectResponse(f"{target}?google=connected", status_code=303)


@router.post("/google/disconnect")
def google_disconnect(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    gcal.disconnect(db)
    return {"ok": True}


@router.post("/google/resync")
def google_resync(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    """Push every event again — useful right after connecting."""
    if not gcal.is_configured() or not gcal.is_connected(db):
        raise HTTPException(status_code=409, detail="Google Calendar is not connected")
    events = svc.all_events(db)
    for event in events:
        gcal.push_event(db, event)
    return {"synced": len(events)}
