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
from app.services import calendar as svc
from app.services import gcal

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
    gcal.remove_event(db, google_id)


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
