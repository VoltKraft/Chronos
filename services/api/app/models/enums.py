import enum


class Role(str, enum.Enum):
    employee = "employee"
    team_lead = "team_lead"
    hr = "hr"
    admin = "admin"


class ShiftType(str, enum.Enum):
    early = "EARLY"
    late = "LATE"
    other = "OTHER"


class LeaveType(str, enum.Enum):
    vacation = "VACATION"
    sick = "SICK"
    other = "OTHER"


class LeaveStatus(str, enum.Enum):
    draft = "DRAFT"
    submitted = "SUBMITTED"
    delegate_review = "DELEGATE_REVIEW"
    tl_review = "TL_REVIEW"
    hr_review = "HR_REVIEW"
    approved = "APPROVED"
    rejected = "REJECTED"
    cancelled = "CANCELLED"
    overridden = "OVERRIDDEN"


class PreferenceType(str, enum.Enum):
    shift_time = "SHIFT_TIME"
    day_off = "DAY_OFF"
    project = "PROJECT"


class CalendarEventType(str, enum.Enum):
    holiday = "HOLIDAY"
    leave = "LEAVE"
    shift = "SHIFT"
    other = "OTHER"


class CalendarSource(str, enum.Enum):
    system = "SYSTEM"
    external = "EXTERNAL"


class AuditAction(str, enum.Enum):
    leave_submit = "leave.submit"
    leave_approve = "leave.approve"
    leave_reject = "leave.reject"
    leave_cancel = "leave.cancel"
    leave_override = "leave.override"
    shift_create = "shift.create"
    shift_update = "shift.update"
    shift_delete = "shift.delete"
    shift_publish = "shift.publish"
    shift_assign = "shift.assign"
    shift_unassign = "shift.unassign"
    preference_create = "preference.create"
    preference_delete = "preference.delete"
    sickness_report = "sickness.report"
    role_change = "user.role_change"
    config_change = "config.change"
    data_export = "data.export"
    data_erase = "data.erase"
