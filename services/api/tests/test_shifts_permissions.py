"""H-05: cross-team leak on /api/shifts/{id}/substitutes.

The bug was an OR guard that let any team lead query any team. After the fix
the ``substitutes`` handler relies on ``_can_manage_team`` alone, which only
returns True for HR/admin or for a TL of the same team.
"""

import inspect
import uuid
from dataclasses import dataclass

from app.routers.shifts import _can_manage_team, substitutes


@dataclass
class Fake:
    role: str
    team_id: uuid.UUID | None = None


def test_can_manage_team_admin_any_team():
    assert _can_manage_team(Fake("admin"), uuid.uuid4())


def test_can_manage_team_hr_any_team():
    assert _can_manage_team(Fake("hr"), uuid.uuid4())


def test_can_manage_team_tl_own_team_only():
    own = uuid.uuid4()
    other = uuid.uuid4()
    assert _can_manage_team(Fake("team_lead", team_id=own), own)
    assert not _can_manage_team(Fake("team_lead", team_id=other), own)


def test_can_manage_team_employee_blocked():
    t = uuid.uuid4()
    assert not _can_manage_team(Fake("employee", team_id=t), t)


def test_substitutes_handler_no_longer_uses_broken_or_guard():
    src = inspect.getsource(substitutes)
    assert "is_tl_or_above" not in src, (
        "substitutes() must use _can_manage_team alone — the old "
        "'not _can_manage_team(...) and not is_tl_or_above(...)' guard "
        "leaked cross-team shifts to any TL"
    )
