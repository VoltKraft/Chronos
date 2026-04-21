"""H-03: session-lifecycle tests (fixation prevention + idle timeout).

All checks are pure-logic — no HTTP, no DB — using lightweight stand-ins for
the ``Request``/``User``/``Session`` objects that ``current_user`` and the
login handler touch. Follows the monkeypatch style of
``tests/test_auth_route_introspection.py`` and ``tests/test_auth_rate_limit.py``.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app import deps
from app.config import settings
from app.routers import auth as auth_router


class FakeSession(dict):
    """Stand-in for Starlette's signed-cookie session — a plain dict is enough.

    The production session quacks like a MutableMapping with a ``clear()``
    method, which ``dict`` already provides.
    """


@dataclass
class FakeRequest:
    session: FakeSession = field(default_factory=FakeSession)


@dataclass
class FakeUser:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    email: str = "victim@example.com"
    role: str = "employee"
    password_hash: str = "argon2-stub"
    deleted_at: Any = None
    failed_login_count: int = 0
    locked_until: Any = None


def _now() -> datetime:
    return datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# current_user: idle-timeout path
# ---------------------------------------------------------------------------


def test_current_user_clears_session_and_401s_when_idle_timeout_exceeded():
    """A stale ``_last_seen`` must trigger a 401 AND wipe the session dict."""
    user = FakeUser()
    req = FakeRequest()
    # Pin the timestamp relative to real wall clock so the comparison against
    # ``datetime.now(timezone.utc)`` inside ``current_user`` is deterministic.
    real_now = int(datetime.now(timezone.utc).timestamp())
    stale = real_now - settings.session_idle_timeout_seconds - 1
    req.session["uid"] = str(user.id)
    req.session["role"] = user.role
    req.session["_login_at"] = stale
    req.session["_last_seen"] = stale

    db = MagicMock()
    db.get.return_value = user

    with pytest.raises(HTTPException) as excinfo:
        deps.current_user(req, db=db)  # type: ignore[arg-type]

    assert excinfo.value.status_code == 401
    # Session was wiped so the browser can't silently reuse it.
    assert "uid" not in req.session
    assert "_last_seen" not in req.session
    # The ORM was never even consulted — we short-circuit on the idle check.
    db.get.assert_not_called()


def test_current_user_refreshes_last_seen_when_within_idle_window():
    """A non-stale ``_last_seen`` causes ``current_user`` to stamp a newer value."""
    user = FakeUser()
    req = FakeRequest()
    # Last seen 60s ago — well within the 30 min default window.
    real_now = int(datetime.now(timezone.utc).timestamp())
    fresh = real_now - 60
    req.session["uid"] = str(user.id)
    req.session["role"] = user.role
    req.session["_login_at"] = fresh
    req.session["_last_seen"] = fresh

    db = MagicMock()
    db.get.return_value = user

    returned = deps.current_user(req, db=db)  # type: ignore[arg-type]

    assert returned is user
    # Stamp got bumped forward — strictly greater than the prior value.
    assert req.session["_last_seen"] > fresh
    # And inside the idle window relative to real "now".
    assert (
        int(datetime.now(timezone.utc).timestamp()) - req.session["_last_seen"]
        <= settings.session_idle_timeout_seconds
    )


# ---------------------------------------------------------------------------
# login: session-fixation prevention
# ---------------------------------------------------------------------------


def test_login_clears_preseeded_session_and_writes_fresh_identity(monkeypatch):
    """H-03: a session pre-seeded by an attacker must not survive login."""
    user = FakeUser()

    # Stub out the dependencies used inside login() so we never touch a DB.
    db = MagicMock()
    scalar = MagicMock()
    scalar.scalar_one_or_none.return_value = user
    db.execute.return_value = scalar

    monkeypatch.setattr(auth_router, "verify_password", lambda _p, _h: True)
    monkeypatch.setattr(auth_router, "is_locked", lambda _u, _n: False)
    monkeypatch.setattr(auth_router, "register_failed_attempt", lambda *_a, **_k: None)
    monkeypatch.setattr(auth_router, "register_successful_login", lambda _u: None)

    req = FakeRequest()
    # Pre-seed the session as an attacker would via a fixation attempt.
    req.session["attacker_injected"] = "bad"
    req.session["uid"] = "00000000-0000-0000-0000-000000000000"

    payload = auth_router.LoginRequest(username="victim@example.com", password="correct-horse")
    # ``@limiter.limit`` wraps the function with a decorator that validates
    # ``request`` is a real Starlette ``Request`` — we sidestep that layer via
    # ``__wrapped__`` because this test exercises the login body, not SlowAPI.
    login_impl = auth_router.login.__wrapped__  # type: ignore[attr-defined]
    returned = login_impl(payload, req, db=db)

    assert returned is user
    # Fixation-seeded key is gone.
    assert "attacker_injected" not in req.session
    # Fresh identity is in place.
    assert req.session["uid"] == str(user.id)
    assert req.session["role"] == user.role
    # Both H-03 timestamps are populated and equal (login == last_seen at T0).
    assert isinstance(req.session["_login_at"], int)
    assert isinstance(req.session["_last_seen"], int)
    assert req.session["_login_at"] == req.session["_last_seen"]
