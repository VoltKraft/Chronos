"""End-to-end leave flow integration test.

Covers the headline path the FS promises:
  login → create leave → submit → HR approves →
  audit chain verifies → GDPR data export includes the leave.

Uses the shared harness in ``conftest.py``: ephemeral Postgres, Alembic at
head, truncated schema per test, cookie-carrying ``TestClient``, CSRF header
auto-wired after login.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.models import AuditEvent, User
from app.models.enums import Role
from app.services import audit as audit_service


def test_employee_leave_approved_by_hr_end_to_end(
    client: TestClient,
    make_user,
    auth_login,
) -> None:
    # --- Cast: an employee who wants holiday, plus an HR approver ---------
    emp_password = "Employee-Pass-1234!"
    hr_password = "HR-Review-Pass-1234!"
    emp = make_user(
        email="emp@chronos.test",
        password=emp_password,
        role=Role.employee,
        first_name="Emma",
        last_name="Ployee",
    )
    hr = make_user(
        email="hr@chronos.test",
        password=hr_password,
        role=Role.hr,
        first_name="Helga",
        last_name="Resource",
    )

    # --- Employee session: create draft leave, submit ---------------------
    auth_login(client, emp.email, emp_password)

    start = date.today() + timedelta(days=7)
    end = start + timedelta(days=2)
    create = client.post(
        "/api/leave-requests",
        json={
            "type": "VACATION",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "reason": "Short break",
            "approver_hr_id": str(hr.id),
        },
    )
    assert create.status_code == 201, create.text
    leave_id = create.json()["id"]
    assert create.json()["status"] == "DRAFT"

    submit = client.post(f"/api/leave-requests/{leave_id}/submit")
    assert submit.status_code == 200, submit.text
    # No delegate, no TL -> goes straight to HR review.
    assert submit.json()["status"] == "HR_REVIEW"

    # Employee logs out so the next login rotates the session cleanly.
    assert client.post("/auth/logout").status_code == 204

    # --- HR session: pick up the request, approve it ----------------------
    auth_login(client, hr.email, hr_password)

    inbox = client.get("/api/leave-requests/inbox")
    assert inbox.status_code == 200, inbox.text
    inbox_ids = [row["id"] for row in inbox.json()]
    assert leave_id in inbox_ids, f"HR inbox missing leave {leave_id}: {inbox_ids}"

    approve = client.post(
        f"/api/leave-requests/{leave_id}/approve",
        json={"reason": "Looks fine"},
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "APPROVED"
    assert approve.json()["decided_at"] is not None

    # --- Audit chain must still verify after both mutations ----------------
    with SessionLocal() as db:
        ok, checked, first_bad = audit_service.verify_chain(db)
        assert ok, f"audit chain broken after {checked} events; first bad={first_bad}"
        # At minimum: submit + approve events for the leave.
        actions = [
            row.action
            for row in db.query(AuditEvent).order_by(AuditEvent.seq).all()
        ]
    assert "leave.submit" in actions, actions
    assert "leave.approve" in actions, actions

    # --- Employee reopens a session; GDPR export contains the leave -------
    assert client.post("/auth/logout").status_code == 204
    auth_login(client, emp.email, emp_password)

    exp = client.get(f"/api/users/{emp.id}/export")
    assert exp.status_code == 200, exp.text
    payload = exp.json()
    assert payload["profile"]["email"] == emp.email
    assert "password_hash" not in payload["profile"]
    leaves = payload["leave_requests"]
    assert any(row["id"] == leave_id for row in leaves), leaves

    # Export itself is audited; chain still holds.
    with SessionLocal() as db:
        ok, _, first_bad = audit_service.verify_chain(db)
        assert ok, f"audit chain broken after export; first bad={first_bad}"
        assert (
            db.query(AuditEvent)
            .filter(AuditEvent.action == "data.export")
            .count()
            >= 1
        )


def test_csrf_header_is_required_for_state_changes(
    client: TestClient,
    make_user,
) -> None:
    """Login endpoint is exempt, but subsequent POSTs need the header."""
    password = "Employee-Pass-1234!"
    emp = make_user(email="noc@chronos.test", password=password)

    r = client.post("/auth/login", json={"username": emp.email, "password": password})
    assert r.status_code == 200
    # Deliberately do NOT fetch the CSRF token — the next POST must be rejected.
    r = client.post(
        "/api/leave-requests",
        json={
            "type": "vacation",
            "start_date": date.today().isoformat(),
            "end_date": date.today().isoformat(),
        },
    )
    assert r.status_code == 403, r.text
    assert "CSRF" in r.json()["detail"]


def test_requires_authentication(client: TestClient) -> None:
    r = client.get("/auth/me")
    assert r.status_code == 401
    # Healthz is always open; anchor that so we don't silently break it.
    r = client.get("/healthz")
    assert r.status_code == 200
