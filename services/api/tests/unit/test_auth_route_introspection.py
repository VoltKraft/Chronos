"""H-02: route-introspection tests for /auth/login.

We only look at the FastAPI router and the app state — no HTTP calls, no DB —
so the checks stay aligned with the pure-logic test style used elsewhere.
"""

import inspect

from fastapi import Request
from fastapi.routing import APIRoute
from slowapi import Limiter

from app.main import app


def _find(path: str, method: str) -> APIRoute:
    for r in app.routes:
        if isinstance(r, APIRoute) and r.path == path and method in r.methods:
            return r
    raise AssertionError(f"no route {method} {path}")


def test_login_route_accepts_request_parameter():
    route = _find("/auth/login", "POST")
    sig = inspect.signature(route.endpoint)
    params = sig.parameters
    assert "request" in params, "SlowAPI requires the handler to expose `request`"
    assert params["request"].annotation is Request


def test_app_has_slowapi_limiter_attached():
    assert hasattr(app.state, "limiter"), "Limiter must be wired on app.state"
    assert isinstance(app.state.limiter, Limiter)


def test_rate_limit_exceeded_handler_is_registered():
    from slowapi.errors import RateLimitExceeded

    assert RateLimitExceeded in app.exception_handlers
