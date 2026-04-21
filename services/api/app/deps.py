import uuid
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User


def _enforce_idle_timeout(request: Request, now: datetime) -> None:
    """H-03: drop the session if the authenticated idle window has elapsed.

    Compares ``now`` against the ``_last_seen`` epoch stamp written on every
    prior authenticated request. When the gap exceeds
    ``SESSION_IDLE_TIMEOUT_SECONDS`` the session is cleared and a 401 is
    raised; the caller is forced to re-authenticate.
    """
    last_seen = request.session.get("_last_seen")
    if last_seen is None:
        return
    try:
        last_seen_int = int(last_seen)
    except (TypeError, ValueError):
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="session invalid"
        )
    if int(now.timestamp()) - last_seen_int > settings.session_idle_timeout_seconds:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired"
        )


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    now = datetime.now(timezone.utc)
    _enforce_idle_timeout(request, now)
    try:
        user_id = uuid.UUID(uid)
    except (TypeError, ValueError):
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session invalid")
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session invalid")
    request.session["_last_seen"] = int(now.timestamp())
    return user
