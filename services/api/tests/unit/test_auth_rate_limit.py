"""H-02: unit tests for the per-user brute-force counter and lockout helpers.

These tests operate on a lightweight stand-in (``FakeUser``) that exposes the
same two columns as :class:`app.models.User`. No database, no SQLAlchemy —
we're only verifying the pure state transitions in
``app.services.auth_rate_limit``.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.services.auth_rate_limit import (
    is_locked,
    register_failed_attempt,
    register_successful_login,
    reset,
)


@dataclass
class FakeUser:
    failed_login_count: int = 0
    locked_until: datetime | None = None


def _now() -> datetime:
    # Fixed aware UTC timestamp — all tests compute deltas from here so nothing
    # depends on real wall-clock time.
    return datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)


def test_fresh_user_is_not_locked():
    assert is_locked(FakeUser(), _now()) is False


def test_failed_attempt_increments_counter_below_threshold():
    user = FakeUser()
    now = _now()
    register_failed_attempt(user, now)
    assert user.failed_login_count == 1
    assert user.locked_until is None
    assert is_locked(user, now) is False


def test_lockout_triggers_exactly_at_threshold():
    user = FakeUser()
    now = _now()
    for _ in range(settings.auth_max_failed_attempts - 1):
        register_failed_attempt(user, now)
    assert user.failed_login_count == settings.auth_max_failed_attempts - 1
    assert user.locked_until is None

    # The Nth failure flips the lock and resets the counter.
    register_failed_attempt(user, now)
    assert user.locked_until is not None
    assert user.failed_login_count == 0


def test_lockout_uses_configured_duration():
    user = FakeUser()
    now = _now()
    for _ in range(settings.auth_max_failed_attempts):
        register_failed_attempt(user, now)
    assert user.locked_until == now + timedelta(seconds=settings.auth_lockout_seconds)


def test_is_locked_is_false_before_any_lock_is_set():
    """Without a ``locked_until`` the predicate is unconditionally False."""
    user = FakeUser(failed_login_count=2, locked_until=None)
    assert is_locked(user, _now()) is False


def test_is_locked_is_true_during_lockout_window():
    now = _now()
    user = FakeUser(locked_until=now + timedelta(seconds=60))
    assert is_locked(user, now) is True
    assert is_locked(user, now + timedelta(seconds=59)) is True


def test_is_locked_is_false_after_lockout_expires():
    now = _now()
    user = FakeUser(locked_until=now + timedelta(seconds=60))
    assert is_locked(user, now + timedelta(seconds=60)) is False  # boundary == "not <"
    assert is_locked(user, now + timedelta(seconds=61)) is False


def test_register_successful_login_clears_state():
    user = FakeUser(failed_login_count=3, locked_until=_now() + timedelta(seconds=30))
    register_successful_login(user)
    assert user.failed_login_count == 0
    assert user.locked_until is None


def test_reset_is_an_alias_of_successful_login():
    user = FakeUser(failed_login_count=4, locked_until=_now() + timedelta(seconds=30))
    reset(user)
    assert user.failed_login_count == 0
    assert user.locked_until is None


def test_lockout_then_further_attempts_restart_counter():
    """After a lockout, subsequent failures build a fresh counter from zero."""
    user = FakeUser()
    now = _now()
    for _ in range(settings.auth_max_failed_attempts):
        register_failed_attempt(user, now)
    assert user.failed_login_count == 0
    assert user.locked_until is not None

    register_failed_attempt(user, now)
    assert user.failed_login_count == 1
