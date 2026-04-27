import uuid
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import Preference, User
from app.models.enums import AuditAction, PreferenceType
from app.permissions import is_hr_or_admin
from app.services import audit

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


class PreferenceIn(BaseModel):
    user_id: uuid.UUID
    preference_type: PreferenceType
    payload: dict[str, Any] = Field(default_factory=dict)
    effective_from: date
    effective_to: date | None = None


class PreferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    preference_type: str
    payload: dict[str, Any]
    effective_from: date
    effective_to: date | None


@router.get("", response_model=list[PreferenceOut])
def list_preferences(
    db: Session = Depends(get_db),
    viewer: User = Depends(current_user),
    user_id: uuid.UUID | None = None,
) -> list[Preference]:
    stmt = select(Preference).where(Preference.deleted_at.is_(None))
    target = user_id or viewer.id
    if target != viewer.id and not is_hr_or_admin(viewer):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return list(
        db.execute(stmt.where(Preference.user_id == target).order_by(Preference.effective_from.desc())).scalars()
    )


def _preference_snapshot(pref: Preference) -> dict[str, Any]:
    return {
        "user_id": str(pref.user_id),
        "preference_type": pref.preference_type,
        "payload": pref.payload,
        "effective_from": pref.effective_from.isoformat(),
        "effective_to": pref.effective_to.isoformat() if pref.effective_to else None,
    }


@router.post("", response_model=PreferenceOut, status_code=status.HTTP_201_CREATED)
def create_preference(
    payload: PreferenceIn, db: Session = Depends(get_db), viewer: User = Depends(current_user)
) -> Preference:
    if payload.user_id != viewer.id and not is_hr_or_admin(viewer):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    pref = Preference(
        user_id=payload.user_id,
        preference_type=payload.preference_type.value,
        payload=payload.payload,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
    )
    db.add(pref)
    db.flush()
    audit.append(
        db,
        actor=viewer,
        action=AuditAction.preference_create,
        target_type="preference",
        target_id=pref.id,
        after=_preference_snapshot(pref),
    )
    db.commit()
    db.refresh(pref)
    return pref


@router.delete("/{pid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_preference(
    pid: uuid.UUID, db: Session = Depends(get_db), viewer: User = Depends(current_user)
) -> None:
    pref = db.get(Preference, pid)
    if pref is None or pref.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    if pref.user_id != viewer.id and not is_hr_or_admin(viewer):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    before = _preference_snapshot(pref)
    pref.deleted_at = datetime.now(timezone.utc)
    audit.append(
        db,
        actor=viewer,
        action=AuditAction.preference_delete,
        target_type="preference",
        target_id=pref.id,
        before=before,
    )
    db.commit()
