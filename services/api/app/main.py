import logging

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.routers import auth, health

logging.basicConfig(level=settings.log_level.upper())

app = FastAPI(title="Chronos API", version="0.1.0")

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie=settings.cookie_name,
    max_age=settings.session_max_age_seconds,
    same_site=settings.cookie_samesite,
    https_only=settings.cookie_secure,
)

app.include_router(health.router)
app.include_router(auth.router)
