from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.admin import verify_token
from app.services.friends import friend_id_from_token


def require_admin(authorization: str = Header(default="")) -> None:
    token = authorization.removeprefix("Bearer ").strip()
    if not token or not verify_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")


def viewer_level(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> str:
    """How much of the site this caller may see.

    admin  -> everything, including private
    friend -> public + friends
    anyone -> public only
    """
    token = authorization.removeprefix("Bearer ").strip()
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
