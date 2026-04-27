"""Sanity checks for enum values — these strings show up in audit logs,
API payloads, and the OpenAPI spec, so regressions in them are breaking changes."""

from app.models.enums import (
    AuditAction,
    CalendarEventType,
    CalendarSource,
    LeaveStatus,
    LeaveType,
    PreferenceType,
    Role,
    ShiftType,
)


def test_role_values():
    assert {r.value for r in Role} == {"employee", "team_lead", "hr", "admin"}


def test_leave_status_covers_full_lifecycle():
    assert {s.value for s in LeaveStatus} >= {
        "DRAFT",
        "SUBMITTED",
        "DELEGATE_REVIEW",
        "TL_REVIEW",
        "HR_REVIEW",
        "APPROVED",
        "REJECTED",
        "CANCELLED",
        "OVERRIDDEN",
    }


def test_leave_type_sick_exists_for_F13():
    values = {t.value for t in LeaveType}
    assert "VACATION" in values
    assert "SICK" in values
    assert "OTHER" in values


def test_shift_type_buckets():
    assert {s.value for s in ShiftType} == {"EARLY", "LATE", "OTHER"}


def test_calendar_types():
    assert CalendarEventType.leave.value == "LEAVE"
    assert CalendarEventType.shift.value == "SHIFT"
    assert CalendarSource.system.value == "SYSTEM"


def test_preference_types():
    assert {p.value for p in PreferenceType} >= {"SHIFT_TIME", "DAY_OFF", "PROJECT"}


def test_audit_action_has_compliance_events():
    assert AuditAction.leave_approve.value == "leave.approve"
    assert AuditAction.leave_reject.value == "leave.reject"
    assert AuditAction.leave_override.value == "leave.override"
    assert AuditAction.data_export.value == "data.export"
    assert AuditAction.data_erase.value == "data.erase"
