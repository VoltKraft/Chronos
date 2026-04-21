import uuid
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import CalendarEvent, Shift, ShiftAssignment, Team, User
from app.models.enums import AuditAction, CalendarEventType, CalendarSource, Role, ShiftType
from app.permissions import is_hr_or_admin, is_tl_or_above, require_tl_or_above
from app.routers.auth import UserPublic
from app.services import audit
from app.services import shift as shift_service

router = APIRouter(prefix="/api/shifts", tags=["shifts"])


class ShiftIn(BaseModel):
    team_id: uuid.UUID
    service_date: date
    shift_type: ShiftType
    start_time: time
    end_time: time
    required_headcount: int = Field(default=1, ge=1, le=20)
    project_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _times(self) -> "ShiftIn":
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class ShiftUpdate(BaseModel):
    start_time: time | None = None
    end_time: time | None = None
    required_headcount: int | None = Field(default=None, ge=1, le=20)
    project_id: uuid.UUID | None = None


class AssignmentIn(BaseModel):
    user_id: uuid.UUID
    note: str | None = None


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shift_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    note: str | None


class ShiftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    team_id: uuid.UUID
    service_date: date
    shift_type: str
    start_time: time
    end_time: time
    required_headcount: int
    project_id: uuid.UUID | None
    assignments: list[AssignmentOut] = []


class PlanIn(BaseModel):
    team_id: uuid.UUID
    period_start: date
    period_end: date
    required_per_shift: int = Field(default=1, ge=1, le=20)
    holidays: list[date] = Field(default_factory=list)


class PlanOut(BaseModel):
    shifts_created: int
    assignments_created: int
    unassigned: list[str]


def _can_manage_team(viewer: User, team_id: uuid.UUID) -> bool:
    if is_hr_or_admin(viewer):
        return True
    if viewer.role == Role.team_lead.value and viewer.team_id == team_id:
        return True
    return False


def _get_shift(db: Session, sid: uuid.UUID) -> Shift:
    s = db.get(Shift, sid)
    if s is None or s.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="shift not found")
    return s


@router.get("", response_model=list[ShiftOut])
def list_shifts(
    db: Session = Depends(get_db),
    viewer: User = Depends(current_user),
    team_id: uuid.UUID | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> list[Shift]:
    stmt = select(Shift).where(Shift.deleted_at.is_(None))
    if team_id is not None:
        stmt = stmt.where(Shift.team_id == team_id)
    elif not is_hr_or_admin(viewer) and viewer.team_id is not None:
        stmt = stmt.where(Shift.team_id == viewer.team_id)
    if period_start is not None:
        stmt = stmt.where(Shift.service_date >= period_start)
    if period_end is not None:
        stmt = stmt.where(Shift.service_date <= period_end)
    return list(db.execute(stmt.order_by(Shift.service_date, Shift.start_time)).scalars())


@router.post("", response_model=ShiftOut, status_code=status.HTTP_201_CREATED)
def create_shift(
    payload: ShiftIn, db: Session = Depends(get_db), viewer: User = Depends(require_tl_or_above())
) -> Shift:
    if not _can_manage_team(viewer, payload.team_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden for this team")
    if db.get(Team, payload.team_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="team not found")
    existing = db.execute(
        select(Shift).where(
            Shift.team_id == payload.team_id,
            Shift.service_date == payload.service_date,
            Shift.shift_type == payload.shift_type.value,
            Shift.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="shift already exists")
    s = Shift(
        team_id=payload.team_id,
        service_date=payload.service_date,
        shift_type=payload.shift_type.value,
        start_time=payload.start_time,
        end_time=payload.end_time,
        required_headcount=payload.required_headcount,
        project_id=payload.project_id,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.patch("/{sid}", response_model=ShiftOut)
def update_shift(
    sid: uuid.UUID,
    payload: ShiftUpdate,
    db: Session = Depends(get_db),
    viewer: User = Depends(require_tl_or_above()),
) -> Shift:
    s = _get_shift(db, sid)
    if not _can_manage_team(viewer, s.team_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(s, key, value)
    db.commit()
    db.refresh(s)
    return s


@router.delete("/{sid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shift(
    sid: uuid.UUID,
    db: Session = Depends(get_db),
    viewer: User = Depends(require_tl_or_above()),
) -> None:
    s = _get_shift(db, sid)
    if not _can_manage_team(viewer, s.team_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    s.deleted_at = datetime.now(timezone.utc)
    db.commit()


@router.post("/{sid}/assignments", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
def assign_user(
    sid: uuid.UUID,
    payload: AssignmentIn,
    db: Session = Depends(get_db),
    viewer: User = Depends(require_tl_or_above()),
) -> ShiftAssignment:
    s = _get_shift(db, sid)
    if not _can_manage_team(viewer, s.team_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    user = db.get(User, payload.user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    existing = db.execute(
        select(ShiftAssignment).where(
            ShiftAssignment.shift_id == s.id, ShiftAssignment.user_id == user.id
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.status != "assigned":
            existing.status = "assigned"
            db.commit()
            db.refresh(existing)
        return existing
    a = ShiftAssignment(shift_id=s.id, user_id=user.id, status="assigned", note=payload.note)
    db.add(a)
    db.flush()
    start_dt = datetime.combine(s.service_date, s.start_time).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(s.service_date, s.end_time).replace(tzinfo=timezone.utc)
    db.add(
        CalendarEvent(
            user_id=user.id,
            event_type=CalendarEventType.shift.value,
            title=f"{s.shift_type} shift",
            starts_at=start_dt,
            ends_at=end_dt,
            source=CalendarSource.system.value,
            shift_id=s.id,
        )
    )
    audit.append(
        db,
        actor=viewer,
        action=AuditAction.shift_assign,
        target_type="shift",
        target_id=s.id,
        after={"user_id": str(user.id)},
    )
    db.commit()
    db.refresh(a)
    return a


@router.delete("/{sid}/assignments/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def unassign_user(
    sid: uuid.UUID,
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    viewer: User = Depends(require_tl_or_above()),
) -> None:
    s = _get_shift(db, sid)
    if not _can_manage_team(viewer, s.team_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    a = db.execute(
        select(ShiftAssignment).where(
            ShiftAssignment.shift_id == s.id, ShiftAssignment.user_id == user_id
        )
    ).scalar_one_or_none()
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="assignment not found")
    a.status = "unassigned"
    db.execute(
        CalendarEvent.__table__.delete().where(
            CalendarEvent.shift_id == s.id, CalendarEvent.user_id == user_id
        )
    )
    audit.append(
        db,
        actor=viewer,
        action=AuditAction.shift_unassign,
        target_type="shift",
        target_id=s.id,
        after={"user_id": str(user_id)},
    )
    db.commit()


@router.get("/{sid}/substitutes", response_model=list[UserPublic])
def substitutes(
    sid: uuid.UUID,
    limit: int = 5,
    db: Session = Depends(get_db),
    viewer: User = Depends(current_user),
) -> list[User]:
    s = _get_shift(db, sid)
    if not _can_manage_team(viewer, s.team_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    exclude = {a.user_id for a in s.assignments if a.status == "assigned"}
    return shift_service.find_substitutes(db, shift=s, exclude=exclude, limit=limit)


@router.post("/plan", response_model=PlanOut)
def run_plan(
    payload: PlanIn, db: Session = Depends(get_db), viewer: User = Depends(require_tl_or_above())
) -> PlanOut:
    if not _can_manage_team(viewer, payload.team_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden for this team")
    if payload.period_start > payload.period_end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="period invalid")
    team = db.get(Team, payload.team_id)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="team not found")
    result = shift_service.plan_period(
        db,
        team=team,
        period_start=payload.period_start,
        period_end=payload.period_end,
        required_per_shift=payload.required_per_shift,
        holidays=set(payload.holidays),
        actor=viewer,
    )
    db.commit()
    return PlanOut(
        shifts_created=result.shifts_created,
        assignments_created=result.assignments_created,
        unassigned=result.unassigned,
    )
