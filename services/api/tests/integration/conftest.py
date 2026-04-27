"""Integration-test harness for the Chronos API.

Boots a throwaway PostgreSQL (via ``testcontainers`` unless
``TEST_DATABASE_URL`` is already set — CI uses the ``services: postgres``
GitHub Actions feature for that), runs Alembic up to ``head``, and exposes
a ``TestClient`` plus user-factory fixtures. Each test starts against a
truncated schema so order-independence holds.

Environment is wired BEFORE any ``app.*`` import — ``app.config.Settings``
reads ``DATABASE_URL``/``SESSION_SECRET`` at instantiation time, and
``app.db.engine`` binds to whatever URL was live when the module was first
imported. We therefore do the env dance at conftest *module load*, which
pytest evaluates before it collects any test modules in this directory.
"""

from __future__ import annotations

import os
import pathlib
import sys
import uuid
from typing import Callable, Iterator

# ---------------------------------------------------------------------------
# Bootstrap: sys.path + env BEFORE any ``app.*`` import.
# ---------------------------------------------------------------------------

# ``services/api`` — three ``parent`` hops up from
# ``services/api/tests/integration/conftest.py``.
_API_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
_container = None

if _TEST_DATABASE_URL is None:
    try:
        from testcontainers.postgres import PostgresContainer  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Integration tests require either a TEST_DATABASE_URL env var "
            "(used by CI where Postgres is a job service) or the "
            "`testcontainers[postgres]` package:\n"
            "  pip install -e '.[dev,integration]'\n"
            "or install it directly:\n"
            "  pip install 'testcontainers[postgres]>=4.8'"
        ) from exc

    _container = PostgresContainer("postgres:18-alpine")
    _container.start()
    # testcontainers defaults to the psycopg2 driver prefix; Chronos runs on
    # psycopg 3, so we swap the dialect before handing the URL to SQLAlchemy.
    _TEST_DATABASE_URL = _container.get_connection_url().replace(
        "postgresql+psycopg2://", "postgresql+psycopg://"
    )

os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
# 48+ chars keeps the prod-mode SESSION_SECRET validator happy if a dev ever
# flips ENV=prod by accident; ENV=dev below bypasses the entropy check anyway.
os.environ.setdefault(
    "SESSION_SECRET",
    "integration-test-secret-integration-test-secret-integration-test-secret",
)
os.environ.setdefault("ENV", "dev")
# TestClient uses http://testserver; Secure cookies would be dropped by httpx.
os.environ.setdefault("COOKIE_SECURE", "false")
# Do not touch external SMTP from the test process.
os.environ.setdefault("SMTP_ENABLED", "false")

# ---------------------------------------------------------------------------
# Now safe to import anything that depends on settings / the engine.
# ---------------------------------------------------------------------------

import pytest  # noqa: E402
from alembic import command as alembic_command  # noqa: E402
from alembic.config import Config as AlembicConfig  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.models.enums import Role  # noqa: E402
from app.security import hash_password  # noqa: E402


def _run_migrations() -> None:
    """Run Alembic ``upgrade head`` against the configured database."""
    cfg = AlembicConfig(str(_API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_API_ROOT / "alembic"))
    alembic_command.upgrade(cfg, "head")


def pytest_configure(config: pytest.Config) -> None:  # noqa: ARG001
    _run_migrations()


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ARG001
    if _container is not None:
        _container.stop()


# ---------------------------------------------------------------------------
# Per-test isolation: truncate everything between tests.
# ---------------------------------------------------------------------------


def _truncate_all() -> None:
    """Drop every row from the public schema, preserve schema + alembic_version.

    ``TRUNCATE ... RESTART IDENTITY CASCADE`` is the fastest reset that still
    honours FK chains and resets sequences. We keep ``alembic_version`` so the
    next test doesn't re-run migrations.
    """
    with engine.begin() as conn:
        names = [
            row[0]
            for row in conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname='public' AND tablename != 'alembic_version'"
                )
            )
        ]
        if names:
            quoted = ", ".join(f'"{n}"' for n in names)
            conn.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def _clean_db() -> Iterator[None]:
    _truncate_all()
    yield


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Cookie-carrying HTTP client bound to the live FastAPI app."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# User factory: keeps tests tight and readable.
# ---------------------------------------------------------------------------

UserFactory = Callable[..., User]


@pytest.fixture
def make_user() -> UserFactory:
    """Return a factory that persists a user with the given role and returns
    a detached ORM instance safe to read outside the session."""

    def _make(
        *,
        email: str | None = None,
        password: str = "Correct-Horse-Battery-Staple-1!",
        role: Role = Role.employee,
        first_name: str = "Test",
        last_name: str = "User",
        team_id: uuid.UUID | None = None,
        department_id: uuid.UUID | None = None,
        must_rotate_password: bool = False,
    ) -> User:
        with SessionLocal() as db:
            user = User(
                email=email or f"{uuid.uuid4().hex[:10]}@chronos.test",
                password_hash=hash_password(password),
                first_name=first_name,
                last_name=last_name,
                role=role.value,
                department_id=department_id,
                team_id=team_id,
                must_rotate_password=must_rotate_password,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            db.expunge(user)
            return user

    return _make


# ---------------------------------------------------------------------------
# Login helper: logs in, fetches the CSRF token, wires the X-CSRF-Token header.
# ---------------------------------------------------------------------------

LoginFn = Callable[[TestClient, str, str], str]


@pytest.fixture
def auth_login() -> LoginFn:
    def _login(c: TestClient, email: str, password: str) -> str:
        resp = c.post("/auth/login", json={"username": email, "password": password})
        assert resp.status_code == 200, resp.text
        tok = c.get("/auth/csrf-token")
        assert tok.status_code == 200, tok.text
        token = tok.json()["csrf_token"]
        c.headers.update({"X-CSRF-Token": token})
        return token

    return _login
