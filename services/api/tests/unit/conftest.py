"""Shared pytest configuration.

The tests here focus on pure business logic (state machines, hash chain,
ICS rendering, RBAC). They set minimal env vars so importing
``app.*`` does not try to reach a live database.
"""

import os
import pathlib
import sys

# Ensure the ``app`` package on the project is importable without installation.
ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://ignored:ignored@localhost:5432/ignored"
)
os.environ.setdefault("SESSION_SECRET", "test-secret-test-secret-test-secret!")
