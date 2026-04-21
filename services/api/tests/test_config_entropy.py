"""H-09: SESSION_SECRET entropy and length guard on non-dev environments."""

import secrets

import pytest
from pydantic import ValidationError

from app.config import Settings, _shannon_entropy


def _kwargs(**overrides):
    base = {"DATABASE_URL": "postgresql+psycopg://x:x@localhost:5432/x"}
    base.update(overrides)
    return base


def test_shannon_entropy_low_on_repeated_chars():
    assert _shannon_entropy("a" * 100) == 0.0


def test_shannon_entropy_high_on_token_urlsafe():
    assert _shannon_entropy(secrets.token_urlsafe(64)) > 4.5


def test_dev_accepts_weak_secret(monkeypatch):
    monkeypatch.delenv("ENV", raising=False)
    s = Settings(**_kwargs(SESSION_SECRET="short", ENV="dev"))
    assert s.session_secret == "short"


def test_prod_rejects_short_secret():
    with pytest.raises(ValidationError) as exc:
        Settings(**_kwargs(SESSION_SECRET="a" * 10, ENV="prod"))
    assert "SESSION_SECRET too short" in str(exc.value)


def test_prod_rejects_low_entropy_even_if_long_enough():
    with pytest.raises(ValidationError) as exc:
        Settings(**_kwargs(SESSION_SECRET="a" * 60, ENV="prod"))
    assert "entropy too low" in str(exc.value)


def test_prod_accepts_strong_random_secret():
    strong = secrets.token_urlsafe(48)
    s = Settings(**_kwargs(SESSION_SECRET=strong, ENV="prod"))
    assert s.session_secret == strong


def test_staging_enforces_same_rules():
    with pytest.raises(ValidationError):
        Settings(**_kwargs(SESSION_SECRET="short", ENV="staging"))
