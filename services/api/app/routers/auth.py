from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User
from app.security import verify_password

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: EmailStr
    password: str


class LoginResponse(BaseModel):
    user_id: str
    email: EmailStr
    role: str


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.execute(select(User).where(User.email == payload.username, User.deleted_at.is_(None))).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    request.session["uid"] = str(user.id)
    request.session["role"] = user.role
    response.status_code = status.HTTP_200_OK
    return LoginResponse(user_id=str(user.id), email=user.email, role=user.role)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/me", response_model=LoginResponse)
def me(request: Request, db: Session = Depends(get_db)) -> LoginResponse:
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    user = db.get(User, uid)
    if user is None or user.deleted_at is not None:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session invalid")
    return LoginResponse(user_id=str(user.id), email=user.email, role=user.role)


# settings is imported so linter sees the dependency; exposed for main.py session config
__all__ = ["router", "settings"]
