import os
import secrets

from fastapi import Cookie, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.admin import verify_token
from app.services.friends import friend_id_from_token

#: The one machine-to-machine credential in this app. See `require_ingest_token`.
INGEST_TOKEN_ENV = "HEALTH_INGEST_TOKEN"


def _bearer(authorization: str, cookie_token: str = "") -> str:
    """The caller's token, from the Authorization header or the session cookie.

    The client still sends the header (localStorage token), but the HttpOnly
    cookie set at login is what survives a cleared localStorage — either proves
    the same session.
    """
    return authorization.removeprefix("Bearer ").strip() or cookie_token.strip()


def require_admin(
    authorization: str = Header(default=""),
    bk_admin: str = Cookie(default=""),
) -> None:
    token = _bearer(authorization, bk_admin)
    if not token or not verify_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")


def require_ingest_token(authorization: str = Header(default="")) -> None:
    """A static bearer token, for the Apple Shortcut that uploads sleep.

    Deliberately **not** the admin key. That login is a key *file* posted as
    multipart, which an iOS Shortcut cannot do, and handing a background
    automation a credential that unlocks his whole private site would be the
    wrong trade in the other direction. So: one long random string, one
    endpoint, no session — scoped to writing health samples and nothing else.

    Read from the environment on every call rather than at import, so rotating
    it is a restart and not a redeploy. No token configured is a **503 naming
    the variable**: the endpoint is not broken, it was never switched on, and
    the person reading that message is the one who can fix it.
    """
    expected = os.getenv(INGEST_TOKEN_ENV, "").strip()
    if not expected:
        raise HTTPException(
            status_code=503, detail=f"{INGEST_TOKEN_ENV} is not configured on the server"
        )
    presented = authorization.removeprefix("Bearer ").strip()
    # Constant-time: this is a long-lived static secret with no rate limit in
    # front of it, which is exactly the shape a timing oracle is useful against.
    if not presented or not secrets.compare_digest(presented, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


def viewer_level(
    authorization: str = Header(default=""),
    bk_admin: str = Cookie(default=""),
    db: Session = Depends(get_db),
) -> str:
    """How much of the site this caller may see.

    admin  -> everything, including private
    friend -> public + friends
    anyone -> public only
    """
    token = _bearer(authorization, bk_admin)
    if not token:
        return "public"
    if verify_token(token):
        return "admin"
    if friend_id_from_token(db, token):
        return "friend"
    return "public"


def visible_levels(level: str) -> list[str]:
    """The set of `visibility` values a viewer at this level may read."""
    if level == "admin":
        return ["public", "friends", "private"]
    if level == "friend":
        return ["public", "friends"]
    return ["public"]


def can_view(visibility: str, level: str) -> bool:
    """May a viewer at `level` see something marked `visibility`?

    The single rule behind every gated read, including a writing's photos —
    an image must be exactly as reachable as the writing it belongs to, no
    more and no less. An unknown visibility is treated as private: a typo in
    the data should hide content, never expose it.
    """
    if visibility not in ("public", "friends", "private"):
        return level == "admin"
    return visibility in visible_levels(level)
