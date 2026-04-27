"""Tests for the leave-request state machine helpers (pure logic)."""

import uuid
from dataclasses import dataclass, field
from datetime import date

from app.models.enums import LeaveStatus
from app.services import leave as leave_service


@dataclass
class FakeRequest:
    approver_delegate_id: uuid.UUID | None = None
    approver_tl_id: uuid.UUID | None = None
    approver_hr_id: uuid.UUID | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    requester_id: uuid.UUID = field(default_factory=uuid.uuid4)
    type: str = "VACATION"
    status: str = LeaveStatus.draft.value
    start_date: date = date(2026, 5, 1)
    end_date: date = date(2026, 5, 3)
    has_certificate: bool = False


def test_next_review_state_prefers_delegate_when_set():
    delegate = uuid.uuid4()
    req = FakeRequest(approver_delegate_id=delegate, approver_tl_id=uuid.uuid4())
    assert leave_service._next_review_state(req) == LeaveStatus.delegate_review.value


def test_next_review_state_falls_through_when_delegate_missing():
    req = FakeRequest(approver_tl_id=uuid.uuid4())
    assert leave_service._next_review_state(req) == LeaveStatus.tl_review.value
    req = FakeRequest(approver_hr_id=uuid.uuid4())
    assert leave_service._next_review_state(req) == LeaveStatus.hr_review.value


def test_advance_review_state_chain():
    tl = uuid.uuid4()
    hr = uuid.uuid4()
    req = FakeRequest(approver_tl_id=tl, approver_hr_id=hr)

    assert leave_service._advance_review_state(LeaveStatus.delegate_review.value, req) == (
        LeaveStatus.tl_review.value
    )
    assert leave_service._advance_review_state(LeaveStatus.tl_review.value, req) == (
        LeaveStatus.hr_review.value
    )
    assert leave_service._advance_review_state(LeaveStatus.hr_review.value, req) == (
        LeaveStatus.approved.value
    )


def test_advance_review_state_skips_missing_tl():
    req = FakeRequest(approver_hr_id=uuid.uuid4())  # no TL
    assert leave_service._advance_review_state(LeaveStatus.delegate_review.value, req) == (
        LeaveStatus.hr_review.value
    )


def test_reviewer_id_returns_correct_approver():
    delegate, tl, hr = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    req = FakeRequest(approver_delegate_id=delegate, approver_tl_id=tl, approver_hr_id=hr)
    assert leave_service._reviewer_id(req, LeaveStatus.delegate_review.value) == delegate
    assert leave_service._reviewer_id(req, LeaveStatus.tl_review.value) == tl
    assert leave_service._reviewer_id(req, LeaveStatus.hr_review.value) == hr


def test_snapshot_includes_required_fields():
    req = FakeRequest(approver_tl_id=uuid.uuid4())
    snap = leave_service._snapshot(req)
    assert set(snap.keys()) >= {
        "id",
        "status",
        "type",
        "requester_id",
        "approver_delegate_id",
        "approver_tl_id",
        "approver_hr_id",
        "start_date",
        "end_date",
        "has_certificate",
    }
    assert snap["start_date"] == "2026-05-01"
