"""RBAC predicate tests (pure, no DB)."""

import uuid
from dataclasses import dataclass

import pytest
from fastapi import HTTPException

from app.permissions import (
    assert_any,
    assert_can_view_user,
    can_view_user,
    is_admin,
    is_hr_or_admin,
    is_tl_or_above,
)


@dataclass
class Person:
    id: uuid.UUID
    role: str
    team_id: uuid.UUID | None = None


def make(role: str, team: uuid.UUID | None = None) -> Person:
    return Person(id=uuid.uuid4(), role=role, team_id=team)


def test_role_predicates():
    assert is_admin(make("admin"))
    assert not is_admin(make("hr"))
    assert is_hr_or_admin(make("hr"))
    assert is_hr_or_admin(make("admin"))
    assert not is_hr_or_admin(make("team_lead"))
    assert is_tl_or_above(make("team_lead"))
    assert is_tl_or_above(make("hr"))
    assert is_tl_or_above(make("admin"))
    assert not is_tl_or_above(make("employee"))


def test_can_view_user_self_always_allowed():
    viewer = make("employee")
    assert can_view_user(viewer, viewer)


def test_can_view_user_hr_sees_everyone():
    assert can_view_user(make("hr"), make("employee"))
    assert can_view_user(make("admin"), make("employee"))


def test_can_view_user_team_lead_restricted_to_own_team():
    t1, t2 = uuid.uuid4(), uuid.uuid4()
    lead = make("team_lead", team=t1)
    assert can_view_user(lead, make("employee", team=t1))
    assert not can_view_user(lead, make("employee", team=t2))


def test_can_view_user_employee_cannot_view_others():
    assert not can_view_user(make("employee"), make("employee"))


def test_assert_raises_http_exception_on_denial():
    viewer = make("employee")
    with pytest.raises(HTTPException) as exc:
        assert_can_view_user(viewer, make("employee"))
    assert exc.value.status_code == 403


def test_assert_any_passes_when_true():
    assert_any(True)  # no exception


def test_assert_any_raises_on_false():
    with pytest.raises(HTTPException) as exc:
        assert_any(False, message="nope")
    assert exc.value.status_code == 403
    assert exc.value.detail == "nope"
