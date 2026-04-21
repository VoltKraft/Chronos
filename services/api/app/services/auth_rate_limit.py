"""H-02: per-user brute-force counter and lockout plus a per-IP SlowAPI limiter.

The pure helpers (`register_failed_attempt`, `register_successful_login`,
`is_locked`, `reset`) read and write two columns on :class:`app.models.User`:

* ``failed_login_count`` — monotonically increasing until the threshold is hit
* ``locked_until`` — aware UTC datetime past which the account is free again

When ``failed_login_count`` reaches ``settings.auth_max_failed_attempts`` the
account is locked for ``settings.auth_lockout_seconds`` and the counter is
reset to zero. The caller is responsible for committing the session; these
helpers mutate the passed-in ORM instance only.

The secondary `limiter` is a SlowAPI :class:`Limiter` keyed by remote IP and is
applied by the login route via ``@limiter.limit("10/minute")``. It runs in
addition to the per-user counter above; the two layers are complementary — a
single attacker behind one IP hits the IP limiter first, a distributed
attacker against one target hits the per-user counter first.
"""

from datetime import datetime, timedelta, timezone

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.models import User

__all__ = [
    "is_locked",
    "limiter",
    "register_failed_attempt",
    "register_successful_login",
    "reset",
]


def is_locked(user: User, now: datetime) -> bool:
    """Return True iff the user is currently inside an active lockout window."""
    if user.locked_until is None:
        return False
    return now < user.locked_until


def register_failed_attempt(user: User, now: datetime) -> None:
    """Increment the failure counter, and lock the account when the threshold is hit.

    When ``failed_login_count`` reaches ``settings.auth_max_failed_attempts`` the
    counter is reset to 0 and ``locked_until`` is set to ``now + lockout_seconds``.
    """
    user.failed_login_count = (user.failed_login_count or 0) + 1
    if user.failed_login_count >= settings.auth_max_failed_attempts:
        user.locked_until = now + timedelta(seconds=settings.auth_lockout_seconds)
        user.failed_login_count = 0


def register_successful_login(user: User) -> None:
    """Clear the counter and any lockout — called on every successful login."""
    user.failed_login_count = 0
    user.locked_until = None


def reset(user: User) -> None:
    """Explicitly clear lockout state. Intended for admin UI / CLI use."""
    register_successful_login(user)


# Per-IP limiter shared across the app. The import-time construction is safe:
# SlowAPI only touches Redis/memory when the first request is handled.
limiter = Limiter(key_func=get_remote_address)
