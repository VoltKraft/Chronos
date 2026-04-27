"""H-10: CSRF middleware tests.

Pure-logic HTTP tests: we assemble a minimal Starlette app that mounts
``SessionMiddleware`` + ``CSRFMiddleware`` + a dummy protected route and drive
it with ``starlette.testclient.TestClient``. We never import
``app.main`` — that would pull in FastAPI routers, SQLAlchemy bindings, and
the rate-limiter, none of which matter for these checks.

Pattern after ``tests/test_auth_route_introspection.py`` for "small, focused,
no DB" testing.
"""

from __future__ import annotations

import inspect
from typing import Any

from fastapi.routing import APIRoute
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.csrf import (
    CSRF_HEADER_NAME,
    CSRF_SESSION_KEY,
    CSRFMiddleware,
    ensure_csrf_token,
)


# ---------------------------------------------------------------------------
# Minimal app fixture
# ---------------------------------------------------------------------------


def _ok(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


async def _seed_session(request: Request) -> JSONResponse:
    """Helper route that lets a test plant state into the signed cookie.

    The TestClient isn't allowed to write to the cookie directly in a way
    that Starlette will accept on a subsequent request (the cookie is signed
    server-side). Instead we hit this route to set session fields, then the
    next request carries the signed cookie automatically.
    """
    body: dict[str, Any] = await request.json()
    for k, v in body.items():
        request.session[k] = v
    return JSONResponse({"session": dict(request.session)})


def _build_app() -> Starlette:
    """Build a Starlette app matching the production middleware ordering.

    Note: because Starlette wraps middleware in reversed order, passing a
    list to the ``middleware=`` constructor kwarg is order-sensitive. The
    FIRST entry is the outermost layer on a request. We want
    ``SessionMiddleware`` outermost so ``CSRFMiddleware`` sees a populated
    ``request.session``.
    """
    routes = [
        Route("/api/users", _ok, methods=["GET", "POST"]),
        Route("/auth/login", _ok, methods=["POST"]),
        Route("/auth/logout", _ok, methods=["POST"]),
        Route("/api/leave-requests/{lid}", _ok, methods=["PATCH", "DELETE"]),
        Route("/_seed", _seed_session, methods=["POST"]),
        Route("/_echo-session", _ok, methods=["GET"]),
    ]
    middleware = [
        Middleware(SessionMiddleware, secret_key="test-secret-for-csrf"),
        Middleware(CSRFMiddleware),
    ]
    return Starlette(routes=routes, middleware=middleware)


def _auth_client(**session_values: Any) -> TestClient:
    """Return a TestClient with a pre-authenticated session cookie."""
    client = TestClient(_build_app())
    # Always include a uid so the middleware treats the caller as authenticated.
    payload = {"uid": "11111111-1111-1111-1111-111111111111", **session_values}
    res = client.post("/_seed", json=payload)
    assert res.status_code == 200
    return client


# ---------------------------------------------------------------------------
# Safe methods & exemptions
# ---------------------------------------------------------------------------


def test_get_passes_without_csrf_header():
    """Safe methods never carry or need a CSRF header."""
    client = _auth_client(**{CSRF_SESSION_KEY: "whatever"})
    res = client.get("/api/users")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_post_login_is_exempt_even_without_session():
    """POST /auth/login must pass through anonymous; it creates the session."""
    client = TestClient(_build_app())  # no session at all
    res = client.post("/auth/login", json={"username": "a@b.c", "password": "x"})
    assert res.status_code == 200


def test_post_logout_is_exempt_even_without_session():
    """POST /auth/logout is intentionally accepted without CSRF under Lax."""
    client = TestClient(_build_app())
    res = client.post("/auth/logout")
    assert res.status_code == 200


def test_unauthenticated_unsafe_request_is_not_403ed_by_csrf():
    """If there's no session, CSRF stays out of the way and lets 401 land."""
    client = TestClient(_build_app())
    res = client.post("/api/users", json={})
    # Our dummy route returns 200 (there's no real auth on it) — the important
    # invariant is that CSRF did NOT fire. In production current_user would
    # 401 here; what matters is we don't shadow that with a spurious 403.
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# Authenticated unsafe methods
# ---------------------------------------------------------------------------


def test_post_with_session_but_no_csrf_secret_rejects_403():
    """Authenticated session with NO ``_csrf`` field -> 403 missing-in-session."""
    client = _auth_client()  # uid set, but no _csrf key
    res = client.post("/api/users", json={})
    assert res.status_code == 403
    assert res.json() == {"detail": "CSRF token missing in session"}


def test_post_with_session_and_secret_but_no_header_rejects_403():
    """Session has a secret but the SPA forgot the header -> same 403."""
    client = _auth_client(**{CSRF_SESSION_KEY: "s3cret-token"})
    res = client.post("/api/users", json={})
    assert res.status_code == 403
    assert res.json() == {"detail": "CSRF token missing in session"}


def test_post_with_matching_header_passes():
    """Authenticated session + matching header -> request sails through."""
    secret = "s3cret-token-aaa"
    client = _auth_client(**{CSRF_SESSION_KEY: secret})
    res = client.post(
        "/api/users",
        json={},
        headers={CSRF_HEADER_NAME: secret},
    )
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_post_with_mismatching_header_rejects_403():
    """Mismatch -> 403 mismatch."""
    client = _auth_client(**{CSRF_SESSION_KEY: "real-secret"})
    res = client.post(
        "/api/users",
        json={},
        headers={CSRF_HEADER_NAME: "forged-token"},
    )
    assert res.status_code == 403
    assert res.json() == {"detail": "CSRF token mismatch"}


def test_patch_and_delete_methods_are_also_guarded():
    """PUT/PATCH/DELETE must go through the same check, not just POST."""
    client = _auth_client(**{CSRF_SESSION_KEY: "s"})
    for method in ("patch", "delete"):
        res = getattr(client, method)("/api/leave-requests/abc")
        assert res.status_code == 403, f"{method} should be guarded"
        assert res.json()["detail"] == "CSRF token missing in session"


# ---------------------------------------------------------------------------
# ensure_csrf_token helper
# ---------------------------------------------------------------------------


def test_ensure_csrf_token_generates_on_missing():
    session: dict[str, Any] = {}
    token = ensure_csrf_token(session)
    assert isinstance(token, str) and len(token) >= 32
    assert session[CSRF_SESSION_KEY] == token


def test_ensure_csrf_token_is_idempotent():
    session: dict[str, Any] = {}
    first = ensure_csrf_token(session)
    second = ensure_csrf_token(session)
    assert first == second
    assert session[CSRF_SESSION_KEY] == first


def test_ensure_csrf_token_replaces_non_string_values():
    """Defensive: corrupt/legacy values in the session don't poison the chain."""
    session: dict[str, Any] = {CSRF_SESSION_KEY: ""}
    token = ensure_csrf_token(session)
    assert token != ""
    assert session[CSRF_SESSION_KEY] == token


# ---------------------------------------------------------------------------
# Constant-time comparison guard
# ---------------------------------------------------------------------------


def test_csrf_middleware_uses_constant_time_compare():
    """The middleware must compare tokens with ``hmac.compare_digest``.

    An ``==`` comparison would leak the secret over a timing channel. We
    inspect the source rather than trying to microbenchmark the running
    middleware — source-level assertion is more reliable in CI.
    """
    from app import csrf

    src = inspect.getsource(csrf)
    assert "hmac.compare_digest" in src, (
        "CSRFMiddleware must use hmac.compare_digest for constant-time "
        "comparison of the stored and supplied tokens"
    )
    # And the naive form must NOT appear as the decision point.
    assert "stored == supplied" not in src
    assert "supplied == stored" not in src


# ---------------------------------------------------------------------------
# Route introspection: /auth/csrf-token
# ---------------------------------------------------------------------------


def test_csrf_token_route_is_registered_and_requires_current_user():
    """Lightweight route-existence check against the real FastAPI app."""
    from app.deps import current_user
    from app.main import app

    route: APIRoute | None = None
    for r in app.routes:
        if isinstance(r, APIRoute) and r.path == "/auth/csrf-token" and "GET" in r.methods:
            route = r
            break
    assert route is not None, "/auth/csrf-token GET must be registered"

    # current_user must appear in the endpoint's dependency chain.
    sig = inspect.signature(route.endpoint)
    dep_callables: list[Any] = []
    for p in sig.parameters.values():
        default = p.default
        # FastAPI wraps deps in ``Depends(...)`` — pull the dependency callable out.
        if hasattr(default, "dependency"):
            dep_callables.append(default.dependency)
    assert current_user in dep_callables, (
        "/auth/csrf-token must depend on current_user so anonymous callers hit 401"
    )


def test_login_seeds_csrf_token_into_session(monkeypatch):
    """H-10: successful login must stamp a ``_csrf`` into the fresh session.

    Mirrors the harness in ``tests/test_session_lifecycle.py`` — we stub out
    password verification and DB access so we only exercise the login body.
    """
    import uuid
    from dataclasses import dataclass, field
    from unittest.mock import MagicMock

    from app.routers import auth as auth_router

    @dataclass
    class FakeUser:
        id: uuid.UUID = field(default_factory=uuid.uuid4)
        email: str = "victim@example.com"
        role: str = "employee"
        password_hash: str = "argon2-stub"
        deleted_at: Any = None
        failed_login_count: int = 0
        locked_until: Any = None

    class FakeSession(dict):
        pass

    @dataclass
    class FakeRequest:
        session: FakeSession = field(default_factory=FakeSession)

    user = FakeUser()
    db = MagicMock()
    scalar = MagicMock()
    scalar.scalar_one_or_none.return_value = user
    db.execute.return_value = scalar

    monkeypatch.setattr(auth_router, "verify_password", lambda _p, _h: True)
    monkeypatch.setattr(auth_router, "is_locked", lambda _u, _n: False)
    monkeypatch.setattr(auth_router, "register_failed_attempt", lambda *_a, **_k: None)
    monkeypatch.setattr(auth_router, "register_successful_login", lambda _u: None)

    req = FakeRequest()
    payload = auth_router.LoginRequest(username="victim@example.com", password="correct-horse")
    login_impl = auth_router.login.__wrapped__  # type: ignore[attr-defined]
    login_impl(payload, req, db=db)

    assert CSRF_SESSION_KEY in req.session
    token = req.session[CSRF_SESSION_KEY]
    assert isinstance(token, str) and len(token) >= 32
