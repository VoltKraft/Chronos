import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import User
from app.models.enums import AuditAction, Role
from app.permissions import (
    assert_can_view_user,
    is_admin,
    is_hr_or_admin,
    require_admin,
    require_hr_or_admin,
)
from app.routers.auth import UserPublic
from app.schemas import Email
from app.security import hash_password, validate_password_strength, verify_password
from app.services import audit

router = APIRouter(prefix="/api/users", tags=["users"])


def _serialise(value):
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


class UserCreate(BaseModel):
    email: Email
    password: str = Field(min_length=8)
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    role: Role = Role.employee
    locale: str = "en"
    time_zone: str = "UTC"
    department_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None


class UserUpdate(BaseModel):
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    locale: str | None = None
    time_zone: str | None = None
    department_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None


class RoleChange(BaseModel):
    role: Role
    reason: str | None = None


class PasswordUpdate(BaseModel):
    new_password: str = Field(min_length=8)


class SelfPasswordChange(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)


class UserDetail(UserPublic):
    model_config = ConfigDict(from_attributes=True)

    created_at: datetime
    updated_at: datetime


@router.get("", response_model=list[UserDetail])
def list_users(
    db: Session = Depends(get_db),
    viewer: User = Depends(current_user),
    team_id: uuid.UUID | None = None,
) -> list[User]:
    stmt = select(User).where(User.deleted_at.is_(None))
    if not is_hr_or_admin(viewer):
        # Team leads see their own team; employees see only self
        if viewer.role == Role.team_lead.value and viewer.team_id:
            stmt = stmt.where(or_(User.team_id == viewer.team_id, User.id == viewer.id))
        else:
            stmt = stmt.where(User.id == viewer.id)
    if team_id is not None:
        stmt = stmt.where(User.team_id == team_id)
    return list(db.execute(stmt.order_by(User.email)).scalars())


@router.post("", response_model=UserDetail, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate, db: Session = Depends(get_db), actor: User = Depends(require_hr_or_admin())
) -> User:
    email = payload.email.lower()
    if db.execute(select(User.id).where(User.email == email)).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already in use")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        role=payload.role.value,
        locale=payload.locale,
        time_zone=payload.time_zone,
        department_id=payload.department_id,
        team_id=payload.team_id,
    )
    db.add(user)
    db.flush()
    audit.append(
        db,
        actor=actor,
        action=AuditAction.config_change,
        target_type="user",
        target_id=user.id,
        after={"email": user.email, "role": user.role},
    )
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserDetail)
def get_user(
    user_id: uuid.UUID, db: Session = Depends(get_db), viewer: User = Depends(current_user)
) -> User:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    assert_can_view_user(viewer, user)
    return user


@router.patch("/{user_id}", response_model=UserDetail)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(current_user),
) -> User:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    if user.id != actor.id and not is_hr_or_admin(actor):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    if (payload.department_id is not None or payload.team_id is not None) and not is_hr_or_admin(actor):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only HR/admin can move users")
    changes = payload.model_dump(exclude_none=True)
    if changes:
        before = {key: _serialise(getattr(user, key)) for key in changes}
        for key, value in changes.items():
            setattr(user, key, value)
        after = {key: _serialise(getattr(user, key)) for key in changes}
        audit.append(
            db,
            actor=actor,
            action=AuditAction.config_change,
            target_type="user",
            target_id=user.id,
            before=before,
            after=after,
        )
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}/role", response_model=UserDetail)
def set_role(
    user_id: uuid.UUID,
    payload: RoleChange,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin()),
) -> User:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    before = {"role": user.role}
    user.role = payload.role.value
    audit.append(
        db,
        actor=actor,
        action=AuditAction.role_change,
        target_type="user",
        target_id=user.id,
        reason=payload.reason,
        before=before,
        after={"role": user.role},
    )
    db.commit()
    db.refresh(user)
    return user


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_my_password(
    payload: SelfPasswordChange,
    db: Session = Depends(get_db),
    actor: User = Depends(current_user),
) -> None:
    """H-04: self-service rotation.

    Verifies the current password, enforces the policy on the new one, and
    stamps ``password_changed_at`` + clears ``must_rotate_password`` so the
    forced-rotate banner goes away. Emits an audit event in the same
    transaction.
    """
    if not verify_password(payload.current_password, actor.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="current password mismatch"
        )
    try:
        validate_password_strength(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    actor.password_hash = hash_password(payload.new_password)
    actor.password_changed_at = datetime.now(timezone.utc)
    actor.must_rotate_password = False
    audit.append(
        db,
        actor=actor,
        action="user.password.changed",
        target_type="user",
        target_id=actor.id,
    )
    db.commit()


@router.put("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def set_password(
    user_id: uuid.UUID,
    payload: PasswordUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(current_user),
) -> None:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    if user.id != actor.id and not is_admin(actor):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    try:
        validate_password_strength(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    user.must_rotate_password = False
    audit.append(
        db,
        actor=actor,
        action="user.password.changed",
        target_type="user",
        target_id=user.id,
    )
    db.commit()


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin()),
) -> None:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    before = {"email": user.email, "role": user.role}
    user.deleted_at = datetime.now(timezone.utc)
    audit.append(
        db,
        actor=actor,
        action=AuditAction.data_erase,
        target_type="user",
        target_id=user.id,
        before=before,
    )
    db.commit()
