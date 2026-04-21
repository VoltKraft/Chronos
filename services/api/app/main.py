import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.csrf import CSRFMiddleware
from app.routers import (
    audit,
    auth,
    calendar,
    delegates,
    exports,
    health,
    leave,
    organization,
    preferences,
    projects,
    reports,
    shifts,
    users,
    workflows,
)
from app.services.auth_rate_limit import limiter

logging.basicConfig(level=settings.log_level.upper())

app = FastAPI(
    title="Chronos API",
    version="0.2.0",
    description="Shift, leave, and sickness planning — FS Phase 1 implementation.",
)


def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": "rate limit exceeded"})


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

# H-10: CSRF enforcement for unsafe methods.
#
# Starlette's ``add_middleware`` inserts at the head of ``user_middleware`` and
# builds the ASGI stack in reversed order, so the LAST middleware added runs
# first on the request. CSRFMiddleware reads ``request.session``, which means
# ``SessionMiddleware`` must be the outer layer -- i.e. added AFTER this one.
# Keep the order: CSRFMiddleware first, SessionMiddleware second.
app.add_middleware(CSRFMiddleware)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie=settings.cookie_name,
    max_age=settings.session_max_age_seconds,
    same_site=settings.cookie_samesite,
    https_only=settings.cookie_secure,
)

for router in (
    health.router,
    auth.router,
    users.router,
    exports.router,
    organization.router,
    projects.router,
    leave.router,
    delegates.router,
    shifts.router,
    preferences.router,
    calendar.router,
    reports.router,
    audit.router,
    workflows.router,
):
    app.include_router(router)
