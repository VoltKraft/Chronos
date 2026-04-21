import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import User, Workflow
from app.permissions import require_hr_or_admin
from app.services import audit

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    definition: dict[str, Any] = Field(default_factory=dict)


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    definition: dict[str, Any] | None = None


class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    definition: dict[str, Any]
    version: int
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


def _get_or_404(db: Session, workflow_id: uuid.UUID) -> Workflow:
    wf = db.get(Workflow, workflow_id)
    if wf is None or wf.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow not found")
    return wf


@router.get("", response_model=list[WorkflowOut])
def list_workflows(db: Session = Depends(get_db), _: User = Depends(current_user)) -> list[Workflow]:
    rows = db.execute(
        select(Workflow).where(Workflow.deleted_at.is_(None)).order_by(Workflow.updated_at.desc())
    ).scalars().all()
    return list(rows)


@router.post("", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
def create_workflow(
    payload: WorkflowCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_hr_or_admin()),
) -> Workflow:
    wf = Workflow(
        name=payload.name,
        description=payload.description,
        definition=payload.definition,
        created_by=user.id,
    )
    db.add(wf)
    db.flush()
    audit.append(
        db,
        actor=user,
        action="workflow.created",
        target_type="workflow",
        target_id=wf.id,
        after={"name": wf.name, "version": wf.version},
    )
    db.commit()
    db.refresh(wf)
    return wf


@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow(
    workflow_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
) -> Workflow:
    return _get_or_404(db, workflow_id)


@router.put("/{workflow_id}", response_model=WorkflowOut)
def update_workflow(
    workflow_id: uuid.UUID,
    payload: WorkflowUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_hr_or_admin()),
) -> Workflow:
    wf = _get_or_404(db, workflow_id)
    before = {"name": wf.name, "version": wf.version}
    changed = False
    if payload.name is not None:
        wf.name = payload.name
        changed = True
    if payload.description is not None:
        wf.description = payload.description
        changed = True
    if payload.definition is not None:
        wf.definition = payload.definition
        changed = True
    if changed:
        wf.version += 1
        audit.append(
            db,
            actor=user,
            action="workflow.updated",
            target_type="workflow",
            target_id=wf.id,
            before=before,
            after={"name": wf.name, "version": wf.version},
        )
    db.commit()
    db.refresh(wf)
    return wf


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(
    workflow_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_hr_or_admin()),
) -> None:
    wf = _get_or_404(db, workflow_id)
    wf.deleted_at = datetime.now(timezone.utc)
    audit.append(
        db,
        actor=user,
        action="workflow.deleted",
        target_type="workflow",
        target_id=wf.id,
        before={"name": wf.name, "version": wf.version},
    )
    db.commit()
