"""Mirror calendar events into Bektas's Google Calendar.

Why it exists: bektas.app cannot ring his phone. Google can. So every event
created here is pushed to his primary calendar with a reminder attached, and
Google does the notifying.

Two design rules:

1. **Config-driven.** No client id/secret in the environment means the calendar
   still works, it just does not sync. Nothing here is a hard dependency.
2. **Never break CRUD.** Sync runs after the database commit and swallows its
   own failures into `last_error`. A Google outage must not stop him from
   writing down a meeting.

Uses urllib rather than a Google SDK: three endpoints, no new dependency in the
production image.
"""

import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.calendar import CalendarEvent
from app.services.calendar import ASTANA, _now
from app.services.settings import delete_setting, get_setting, set_setting

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
EVENTS_ENDPOINT = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
SCOPE = "https://www.googleapis.com/auth/calendar.events"

DEFAULT_REDIRECT_URI = "https://bektas.app/api/calendar/google/callback"
HTTP_TIMEOUT = 10

# Settings keys
REFRESH_TOKEN = "google_refresh_token"
CONNECTED_AT = "google_connected_at"
OAUTH_STATE = "google_oauth_state"
LAST_ERROR = "google_last_error"

# Access tokens live an hour; cache one rather than trading the refresh token
# on every event write. In-memory on purpose — losing it costs one round trip.
_access_token_cache: dict[str, float | str] = {}


class GoogleNotConfigured(RuntimeError):
    pass


class GoogleError(RuntimeError):
    pass


def client_id() -> str:
    return os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()


def client_secret() -> str:
    return os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()


def redirect_uri() -> str:
    return os.getenv("GOOGLE_REDIRECT_URI", DEFAULT_REDIRECT_URI).strip()


def is_configured() -> bool:
    return bool(client_id() and client_secret())


def is_connected(db: Session) -> bool:
    return bool(get_setting(db, REFRESH_TOKEN))


def _post_form(url: str, fields: dict[str, str]) -> dict:
    data = urllib.parse.urlencode(fields).encode("ascii")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise GoogleError(exc.read().decode("utf-8", "ignore")[:300]) from exc
    except OSError as exc:
        raise GoogleError(str(exc)) from exc


def _api(token: str, url: str, method: str = "GET", body: dict | None = None) -> dict:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=payload, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise GoogleError(f"{exc.code}: {exc.read().decode('utf-8', 'ignore')[:300]}") from exc
    except OSError as exc:
        raise GoogleError(str(exc)) from exc


# --- OAuth dance ---


def build_auth_url(db: Session) -> str:
    if not is_configured():
        raise GoogleNotConfigured("GOOGLE_OAUTH_CLIENT_ID / _SECRET are not set")

    state = secrets.token_urlsafe(24)
    set_setting(db, OAUTH_STATE, state)

    params = {
        "client_id": client_id(),
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": SCOPE,
        # offline + consent is what actually returns a refresh token; without
        # prompt=consent Google omits it on every re-authorization.
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"


def complete_auth(db: Session, code: str, state: str) -> None:
    if not is_configured():
        raise GoogleNotConfigured("GOOGLE_OAUTH_CLIENT_ID / _SECRET are not set")

    expected = get_setting(db, OAUTH_STATE)
    if not expected or not secrets.compare_digest(state, expected):
        raise GoogleError("State mismatch — start the connection again")
    delete_setting(db, OAUTH_STATE)

    tokens = _post_form(
        TOKEN_ENDPOINT,
        {
            "code": code,
            "client_id": client_id(),
            "client_secret": client_secret(),
            "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code",
        },
    )
    refresh = tokens.get("refresh_token")
    if not refresh:
        raise GoogleError(
            "Google returned no refresh token. Remove the app's access at "
            "myaccount.google.com/permissions and connect again."
        )

    set_setting(db, REFRESH_TOKEN, refresh)
    set_setting(db, CONNECTED_AT, _now())
    delete_setting(db, LAST_ERROR)
    _access_token_cache.clear()


def disconnect(db: Session) -> None:
    delete_setting(db, REFRESH_TOKEN)
    delete_setting(db, CONNECTED_AT)
    delete_setting(db, LAST_ERROR)
    _access_token_cache.clear()


def _access_token(db: Session) -> str:
    cached = _access_token_cache.get("token")
    expires = float(_access_token_cache.get("expires_at", 0) or 0)
    if cached and expires > time.time() + 60:
        return str(cached)

    refresh = get_setting(db, REFRESH_TOKEN)
    if not refresh:
        raise GoogleNotConfigured("Google Calendar is not connected")

    tokens = _post_form(
        TOKEN_ENDPOINT,
        {
            "refresh_token": refresh,
            "client_id": client_id(),
            "client_secret": client_secret(),
            "grant_type": "refresh_token",
        },
    )
    token = tokens.get("access_token")
    if not token:
        raise GoogleError("No access token in Google's response")

    _access_token_cache["token"] = token
    _access_token_cache["expires_at"] = time.time() + float(tokens.get("expires_in", 3600))
    return token


# --- Mirroring ---


def _event_body(event: CalendarEvent) -> dict:
    body: dict = {
        "summary": event.title,
        "description": event.notes or "",
        # So he can tell at a glance where an entry came from.
        "source": {"title": "bektas.app", "url": "https://bektas.app"},
    }

    if event.all_day:
        start_date = event.starts_at[:10]
        # Google's all-day end date is exclusive.
        end_date = (event.ends_at or event.starts_at)[:10]
        if end_date <= start_date:
            end_date = (
                datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=1)
            ).strftime("%Y-%m-%d")
        body["start"] = {"date": start_date}
        body["end"] = {"date": end_date}
    else:
        start = datetime.fromisoformat(event.starts_at)
        end = (
            datetime.fromisoformat(event.ends_at)
            if event.ends_at
            else start + timedelta(hours=1)
        )
        body["start"] = {"dateTime": start.isoformat(), "timeZone": str(ASTANA)}
        body["end"] = {"dateTime": end.isoformat(), "timeZone": str(ASTANA)}

    if event.reminder_minutes is not None:
        body["reminders"] = {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": event.reminder_minutes}],
        }
    else:
        body["reminders"] = {"useDefault": True}

    return body


def push_event(db: Session, event: CalendarEvent) -> None:
    """Create or update the Google copy. Failures are recorded, never raised."""
    if not is_configured() or not is_connected(db):
        return

    try:
        token = _access_token(db)
        body = _event_body(event)
        if event.google_event_id:
            result = _api(
                token,
                f"{EVENTS_ENDPOINT}/{urllib.parse.quote(event.google_event_id)}",
                method="PATCH",
                body=body,
            )
        else:
            result = _api(token, EVENTS_ENDPOINT, method="POST", body=body)

        google_id = result.get("id")
        if google_id and google_id != event.google_event_id:
            event.google_event_id = google_id
            db.commit()
        delete_setting(db, LAST_ERROR)
    except (GoogleError, GoogleNotConfigured) as exc:
        _record_error(db, event, exc)


def remove_event(db: Session, google_event_id: str | None) -> None:
    if not google_event_id or not is_configured() or not is_connected(db):
        return
    try:
        token = _access_token(db)
        _api(
            token,
            f"{EVENTS_ENDPOINT}/{urllib.parse.quote(google_event_id)}",
            method="DELETE",
        )
        delete_setting(db, LAST_ERROR)
    except (GoogleError, GoogleNotConfigured) as exc:
        set_setting(db, LAST_ERROR, str(exc)[:300])


def _record_error(db: Session, event: CalendarEvent, exc: Exception) -> None:
    message = str(exc)[:300]
    # A 404 means the Google copy was deleted from the phone; drop the stale id
    # so the next save recreates it instead of failing forever.
    if message.startswith("404") and event.google_event_id:
        event.google_event_id = None
        db.commit()
    set_setting(db, LAST_ERROR, message)


def status(db: Session) -> dict:
    return {
        "configured": is_configured(),
        "connected": is_connected(db),
        "connected_at": get_setting(db, CONNECTED_AT),
        "last_error": get_setting(db, LAST_ERROR),
        "redirect_uri": redirect_uri(),
    }
