"""GDPR-compliant user data export (FS §7.1)."""

import json
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import CalendarEvent, LeaveRequest, Preference, ShiftAssignment, User
from app.models.enums import AuditAction
from app.permissions import is_admin
from app.services import audit

router = APIRouter(prefix="/api/users", tags=["users"])


def _serialise(value):
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _row_to_dict(obj) -> dict:
    return {c.name: _serialise(getattr(obj, c.name)) for c in obj.__table__.columns}


@router.get("/{user_id}/export")
def export_user_data(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    viewer: User = Depends(current_user),
) -> Response:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    if viewer.id != user.id and not is_admin(viewer):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    profile = _row_to_dict(user)
    profile.pop("password_hash", None)
    leave = [
        _row_to_dict(l)
        for l in db.execute(select(LeaveRequest).where(LeaveRequest.requester_id == user_id)).scalars()
    ]
    preferences = [
        _row_to_dict(p)
        for p in db.execute(select(Preference).where(Preference.user_id == user_id)).scalars()
    ]
    events = [
        _row_to_dict(e)
        for e in db.execute(select(CalendarEvent).where(CalendarEvent.user_id == user_id)).scalars()
    ]
    assignments = [
        _row_to_dict(a)
        for a in db.execute(select(ShiftAssignment).where(ShiftAssignment.user_id == user_id)).scalars()
    ]
    payload = {
        "schema_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "leave_requests": leave,
        "preferences": preferences,
        "calendar_events": events,
        "shift_assignments": assignments,
    }
    audit.append(
        db, actor=viewer, action=AuditAction.data_export, target_type="user", target_id=user_id
    )
    db.commit()
    body = json.dumps(payload, indent=2)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=chronos-export-{user_id}.json"},
    )
