import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.csrf import ensure_csrf_token
from app.db import get_db
from app.deps import current_user
from app.models import User
from app.schemas import Email
from app.security import verify_password
from app.services.auth_rate_limit import (
    is_locked,
    limiter,
    register_failed_attempt,
    register_successful_login,
)

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: Email
    password: str


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: Email
    first_name: str | None = None
    last_name: str | None = None
    role: str
    locale: str
    time_zone: str
    department_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    # H-04: surface the forced-rotation flag so the SPA can bounce the user
    # to a change-password page before letting them work.
    must_rotate_password: bool = False


_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
)


@router.post("/auth/login", response_model=UserPublic)
@limiter.limit("10/minute")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> User:
    user = db.execute(
        select(User).where(User.email == payload.username.lower(), User.deleted_at.is_(None))
    ).scalar_one_or_none()
    if user is None:
        raise _INVALID_CREDENTIALS

    now = datetime.now(timezone.utc)

    # Active lockout: reject without leaking whether the password was right.
    if is_locked(user, now):
        raise _INVALID_CREDENTIALS

    if not verify_password(payload.password, user.password_hash):
        register_failed_attempt(user, now)
        db.commit()
        raise _INVALID_CREDENTIALS

    # Correct password — clear any stale counter / expired lockout before proceeding.
    register_successful_login(user)
    db.commit()

    # H-03: defeat session fixation by wiping any pre-seeded session data
    # before writing the authenticated identity. Starlette's signed-cookie
    # session has no server-side id, so a full clear + fresh assignment is
    # the equivalent of a rotate-on-auth.
    request.session.clear()
    login_epoch = int(now.timestamp())
    request.session["uid"] = str(user.id)
    request.session["role"] = user.role
    request.session["_login_at"] = login_epoch
    request.session["_last_seen"] = login_epoch
    # H-10: seed a fresh CSRF secret into the rotated session so the SPA can
    # pick it up immediately via GET /auth/csrf-token (or we could embed it in
    # the login response, but a separate endpoint keeps the login schema
    # stable for existing callers).
    ensure_csrf_token(request.session)
    return user


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/me", response_model=UserPublic)
def me(user: User = Depends(current_user)) -> User:
    return user


class CsrfTokenResponse(BaseModel):
    csrf_token: str


@router.get("/auth/csrf-token", response_model=CsrfTokenResponse)
def csrf_token(
    request: Request,
    _user: User = Depends(current_user),
) -> CsrfTokenResponse:
    """Return the session's CSRF token, minting one if necessary.

    Protected by ``current_user`` so only authenticated sessions can obtain a
    token. ``ensure_csrf_token`` writes the secret back into the session on
    first read, so subsequent calls return the same value until logout.
    """
    token = ensure_csrf_token(request.session)
    return CsrfTokenResponse(csrf_token=token)
