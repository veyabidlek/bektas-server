from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.schemas.friend import FriendOut
from app.services import admin as admin_svc
from app.services import friends as svc

router = APIRouter(prefix="/api/friends", tags=["friends"])


class FriendCreate(BaseModel):
    name: str


class FriendLogin(BaseModel):
    code: str


@router.post("/login")
def friend_login(
    data: FriendLogin,
    request: Request,
    db: Session = Depends(get_db),
):
    """Exchange a friend code for a long-lived viewer token.

    Shares the admin login's per-IP rate limiter so codes cannot be brute-forced.
    """
    ip = request.client.host if request.client else "unknown"

    blocked = admin_svc.check_rate_limit(ip)
    if blocked:
        raise HTTPException(status_code=429, detail=blocked)

    friend = svc.verify_code(db, data.code.strip())
    if not friend:
        admin_svc.record_failed_attempt(ip)
        raise HTTPException(status_code=401, detail="Invalid code")

    admin_svc.clear_attempts(ip)
    return {"token": svc.create_token(friend), "name": friend.name}


@router.get("/verify")
def verify_friend(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
):
    token = authorization.removeprefix("Bearer ").strip()
    return {"valid": bool(token) and bool(svc.friend_id_from_token(db, token))}


@router.get("", response_model=list[FriendOut])
def list_friends(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    return svc.list_friends(db)


@router.post("", response_model=FriendOut, status_code=201)
def create_friend(
    data: FriendCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name is required")
    return svc.create_friend(db, name)


@router.patch("/{friend_id}/revoke", response_model=FriendOut)
def toggle_revoke(
    friend_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    friend = next((f for f in svc.list_friends(db) if f.id == friend_id), None)
    if not friend:
        raise HTTPException(status_code=404, detail="Friend not found")
    return svc.set_revoked(db, friend_id, not friend.revoked)


@router.delete("/{friend_id}", status_code=204)
def delete_friend(
    friend_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if not svc.delete_friend(db, friend_id):
        raise HTTPException(status_code=404, detail="Friend not found")
