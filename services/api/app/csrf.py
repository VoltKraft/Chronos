"""H-10: CSRF protection middleware for unsafe HTTP methods.

Chronos rides on Starlette's signed-cookie session with ``SameSite=Lax``. Lax
keeps cross-site top-level POSTs out, but doesn't cover all unsafe methods and
doesn't defend against form-triggered CSRF from a compromised same-site
surface. We therefore enforce a double-submit-style CSRF token: a per-session
secret lives in the signed cookie, and the SPA must echo it back via the
``X-CSRF-Token`` header on every POST/PUT/PATCH/DELETE.

Token lifecycle:
    * Login regenerates the session and stamps a new ``_csrf`` via
      :func:`ensure_csrf_token`.
    * ``GET /auth/csrf-token`` returns the current token (creating one if
      absent) so the SPA can hydrate its cache after a cold start.
    * Logout wipes the session -> wipes the CSRF secret with it.
"""

from __future__ import annotations

import hmac
import secrets
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Methods that RFC 7231 marks as "safe"; they never mutate state so they skip
# CSRF entirely. OPTIONS is routinely sent by preflight and must not carry a
# token. TRACE is here for completeness even though FastAPI never exposes it.
_SAFE_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# Endpoints that must work without a pre-existing session. Login has no session
# yet, and logout intentionally tears the session down; both are accepted under
# the SameSite=Lax cookie's baseline protection.
_EXEMPT_PATHS: frozenset[str] = frozenset({"/auth/login", "/auth/logout"})

# Header the SPA uses to echo the session's CSRF secret back to us.
CSRF_HEADER_NAME: str = "X-CSRF-Token"

# Session key holding the per-session secret.
CSRF_SESSION_KEY: str = "_csrf"


def ensure_csrf_token(session: Any) -> str:
    """Return the session's CSRF token, generating and caching one if missing.

    ``session`` is Starlette's signed-cookie mapping (a plain ``dict`` under
    the hood). We mutate it in place so the caller's enclosing request will
    re-emit the cookie with the new secret on the response trip.

    Uses :func:`secrets.token_urlsafe` (32 random bytes -> 43 base64url chars)
    so the token is cryptographically random and safe to ship in a header.
    """
    token = session.get(CSRF_SESSION_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def _reject(detail: str) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": detail})


class CSRFMiddleware(BaseHTTPMiddleware):
    """Enforce a CSRF header on authenticated state-changing requests.

    Ordering note: this middleware depends on ``request.session`` being
    populated, which Starlette's ``SessionMiddleware`` arranges. Because
    Starlette's ``add_middleware`` inserts at the head of the list and builds
    the stack by wrapping in reversed order, the LAST call to
    ``add_middleware`` runs first on the request. We therefore register
    ``CSRFMiddleware`` BEFORE ``SessionMiddleware`` in ``main.py``, which
    makes SessionMiddleware the outer layer -- by the time this middleware's
    ``dispatch`` runs, ``request.session`` is already a mutable mapping.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        method = request.method.upper()
        if method in _SAFE_METHODS:
            return await call_next(request)

        path = request.url.path
        # We only guard the API and auth surfaces. Everything else (e.g. the
        # SPA itself, the healthz probe) rides under Traefik routing and has
        # no session cookie attached.
        if not (path.startswith("/api/") or path.startswith("/auth/")):
            return await call_next(request)

        # Unauthenticated exemptions: login has no session yet; logout
        # deliberately clears the session.
        if path in _EXEMPT_PATHS:
            return await call_next(request)

        session = request.session
        # No session at all -> downstream ``current_user`` will 401 us; we
        # must not shadow that with a 403, otherwise probe responses diverge
        # between authenticated and unauthenticated callers.
        if not session.get("uid"):
            return await call_next(request)

        stored = session.get(CSRF_SESSION_KEY)
        if not isinstance(stored, str) or not stored:
            return _reject("CSRF token missing in session")

        supplied = request.headers.get(CSRF_HEADER_NAME)
        if not supplied:
            return _reject("CSRF token missing in session")

        # Constant-time comparison defeats timing oracles on the secret.
        if not hmac.compare_digest(stored, supplied):
            return _reject("CSRF token mismatch")

        return await call_next(request)
