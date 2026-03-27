from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.services import admin as svc

router = APIRouter(prefix="/api/admin", tags=["admin"])


class LoginRequest(BaseModel):
    passcode: str


class LoginResponse(BaseModel):
    token: str


class VerifyResponse(BaseModel):
    valid: bool


@router.post("/login", response_model=LoginResponse)
def login(data: LoginRequest, request: Request):
    ip = request.client.host if request.client else "unknown"

    rate_error = svc.check_rate_limit(ip)
    if rate_error:
        raise HTTPException(status_code=429, detail=rate_error)

    if not svc.verify_passcode(data.passcode):
        svc.record_failed_attempt(ip)
        raise HTTPException(status_code=401, detail="Invalid passcode")

    svc.clear_attempts(ip)
    token = svc.create_token()
    return LoginResponse(token=token)


@router.get("/verify", response_model=VerifyResponse)
def verify(authorization: str = Header(default="")):
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        return VerifyResponse(valid=False)
    return VerifyResponse(valid=svc.verify_token(token))
