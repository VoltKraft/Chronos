"""H-07 — every mutating config endpoint must call audit.append.

Two layers:

1. A handful of explicit tests for specific endpoints, so a rename or signature
   change fails loudly against the expected contract.
2. A route-introspection spider that walks ``app.main.app.routes`` and asserts
   every POST/PUT/PATCH/DELETE endpoint either calls ``audit.append`` directly
   in its source or is listed in ``AUDIT_EXEMPT`` with a reason. The spider
   catches the class of gap the shifts/preferences routers had.
"""
from __future__ import annotations

import inspect
from typing import Iterator

from fastapi.routing import APIRoute

from app.main import app
from app.routers import delegates as delegates_router
from app.routers import preferences as preferences_router
from app.routers import shifts as shifts_router
from app.routers import users as users_router


def _source_of(fn) -> str:
    return inspect.getsource(fn)


# ---------------------------------------------------------------------------
# Layer 1 — explicit per-endpoint regression guards.
# ---------------------------------------------------------------------------

def test_users_update_user_audits_changes():
    src = _source_of(users_router.update_user)
    assert "audit.append" in src
    assert "AuditAction.config_change" in src
    assert 'target_type="user"' in src


def test_delegates_create_audits():
    src = _source_of(delegates_router.create_delegate)
    assert "audit.append" in src
    assert "AuditAction.config_change" in src
    assert 'target_type="delegate"' in src


def test_delegates_delete_audits():
    src = _source_of(delegates_router.delete_delegate)
    assert "audit.append" in src
    assert "AuditAction.config_change" in src
    assert 'target_type="delegate"' in src


def test_users_set_role_audits():
    src = _source_of(users_router.set_role)
    assert "audit.append" in src
    assert "AuditAction.role_change" in src


def test_users_deactivate_audits():
    src = _source_of(users_router.deactivate)
    assert "audit.append" in src
    assert "AuditAction.data_erase" in src


def test_shifts_create_audits():
    src = _source_of(shifts_router.create_shift)
    assert "audit.append" in src
    assert "AuditAction.shift_create" in src
    assert 'target_type="shift"' in src


def test_shifts_update_audits():
    src = _source_of(shifts_router.update_shift)
    assert "audit.append" in src
    assert "AuditAction.shift_update" in src


def test_shifts_delete_audits():
    src = _source_of(shifts_router.delete_shift)
    assert "audit.append" in src
    assert "AuditAction.shift_delete" in src


def test_preferences_create_audits():
    src = _source_of(preferences_router.create_preference)
    assert "audit.append" in src
    assert "AuditAction.preference_create" in src


def test_preferences_delete_audits():
    src = _source_of(preferences_router.delete_preference)
    assert "audit.append" in src
    assert "AuditAction.preference_delete" in src


# ---------------------------------------------------------------------------
# Layer 2 — route-introspection spider.
# ---------------------------------------------------------------------------

# Each entry is (METHOD, PATH) with a reason the endpoint is allowed to
# exist without a direct ``audit.append`` call in the endpoint function. The
# reason is informational only, but keeping it forces contributors to justify
# any exemption they add.
AUDIT_EXEMPT: dict[tuple[str, str], str] = {
    ("POST", "/auth/login"): (
        "Security event; failed/successful attempts tracked via rate-limit "
        "counters and SIEM-style logs, not the business audit chain."
    ),
    ("POST", "/auth/logout"): (
        "Session teardown only; no business state change to audit."
    ),
    ("POST", "/api/leave-requests"): (
        "Creates LeaveRequest in DRAFT state; audited at POST /submit."
    ),
    ("PATCH", "/api/leave-requests/{lid}"): (
        "Edits DRAFT only (rejected on other states); audited at POST /submit."
    ),
    ("POST", "/api/leave-requests/{lid}/submit"): (
        "Audits via app.services.leave.submit."
    ),
    ("POST", "/api/leave-requests/{lid}/approve"): (
        "Audits via app.services.leave.approve."
    ),
    ("POST", "/api/leave-requests/{lid}/reject"): (
        "Audits via app.services.leave.reject."
    ),
    ("POST", "/api/leave-requests/{lid}/cancel"): (
        "Audits via app.services.leave.cancel."
    ),
    ("POST", "/api/leave-requests/{lid}/override"): (
        "Audits via app.services.leave.override."
    ),
    ("POST", "/api/shifts/plan"): (
        "Audits via app.services.shift.plan_period (shift.publish event)."
    ),
}

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def _iter_mutating_routes() -> Iterator[tuple[str, str, object]]:
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = route.methods or set()
        for method in methods:
            if method in _MUTATING:
                yield method, route.path, route.endpoint


def test_every_mutating_endpoint_audits_or_is_exempt():
    missing: list[str] = []
    unused_exemptions = set(AUDIT_EXEMPT.keys())
    for method, path, fn in _iter_mutating_routes():
        key = (method, path)
        if key in AUDIT_EXEMPT:
            unused_exemptions.discard(key)
            continue
        src = _source_of(fn)
        if "audit.append" in src:
            continue
        missing.append(f"{method} {path} -> {fn.__module__}:{fn.__qualname__}")

    assert not missing, (
        "Mutating endpoint(s) without a visible audit.append call and not "
        "listed in AUDIT_EXEMPT. Either add audit.append inside the handler "
        "or, if the endpoint intentionally delegates to a service that "
        "audits, add an AUDIT_EXEMPT entry with a reason:\n  - "
        + "\n  - ".join(missing)
    )
    assert not unused_exemptions, (
        "AUDIT_EXEMPT entries no longer match any registered route "
        "(renamed or removed endpoint?). Remove stale entries:\n  - "
        + "\n  - ".join(f"{m} {p}" for m, p in sorted(unused_exemptions))
    )
