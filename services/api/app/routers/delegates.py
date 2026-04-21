import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import Delegate, User
from app.models.enums import AuditAction
from app.permissions import is_hr_or_admin
from app.services import audit

router = APIRouter(prefix="/api/delegates", tags=["delegates"])


class DelegateIn(BaseModel):
    principal_id: uuid.UUID
    delegate_user_id: uuid.UUID
    valid_from: date
    valid_to: date

    @model_validator(mode="after")
    def _check(self) -> "DelegateIn":
        if self.valid_from > self.valid_to:
            raise ValueError("valid_from must not be after valid_to")
        if self.principal_id == self.delegate_user_id:
            raise ValueError("principal and delegate must differ")
        return self


class DelegateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    principal_id: uuid.UUID
    delegate_user_id: uuid.UUID
    valid_from: date
    valid_to: date


@router.get("", response_model=list[DelegateOut])
def list_delegates(
    db: Session = Depends(get_db), viewer: User = Depends(current_user)
) -> list[Delegate]:
    stmt = select(Delegate).where(Delegate.deleted_at.is_(None))
    if not is_hr_or_admin(viewer):
        stmt = stmt.where(
            or_(Delegate.principal_id == viewer.id, Delegate.delegate_user_id == viewer.id)
        )
    return list(db.execute(stmt.order_by(Delegate.valid_from.desc())).scalars())


@router.post("", response_model=DelegateOut, status_code=status.HTTP_201_CREATED)
def create_delegate(
    payload: DelegateIn,
    db: Session = Depends(get_db),
    viewer: User = Depends(current_user),
) -> Delegate:
    if payload.principal_id != viewer.id and not is_hr_or_admin(viewer):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="cannot create for others")
    if db.get(User, payload.principal_id) is None or db.get(User, payload.delegate_user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    d = Delegate(
        principal_id=payload.principal_id,
        delegate_user_id=payload.delegate_user_id,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
    )
    db.add(d)
    db.flush()
    audit.append(
        db,
        actor=viewer,
        action=AuditAction.config_change,
        target_type="delegate",
        target_id=d.id,
        after={
            "principal_id": str(d.principal_id),
            "delegate_user_id": str(d.delegate_user_id),
            "valid_from": d.valid_from.isoformat(),
            "valid_to": d.valid_to.isoformat(),
        },
    )
    db.commit()
    db.refresh(d)
    return d


@router.delete("/{delegate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_delegate(
    delegate_id: uuid.UUID,
    db: Session = Depends(get_db),
    viewer: User = Depends(current_user),
) -> None:
    d = db.get(Delegate, delegate_id)
    if d is None or d.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    if d.principal_id != viewer.id and not is_hr_or_admin(viewer):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    d.deleted_at = datetime.now(timezone.utc)
    audit.append(
        db,
        actor=viewer,
        action=AuditAction.config_change,
        target_type="delegate",
        target_id=d.id,
        before={
            "principal_id": str(d.principal_id),
            "delegate_user_id": str(d.delegate_user_id),
        },
    )
    db.commit()
