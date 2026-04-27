"""Pure-logic pytest configuration.

Tests in this subtree cover state machines, hash chain maths, ICS
rendering, RBAC predicates, and similar helpers — none of them need a
live database. We poke in minimal env defaults so importing
``app.*`` does not raise during ``Settings`` validation.

Integration tests that do need a live Postgres live under
``tests/integration`` and manage their own environment there.
"""

import os
import pathlib
import sys

# Ensure the ``app`` package is importable without installing the project.
# ``__file__`` is ``services/api/tests/unit/conftest.py``; three ``parent``
# hops land us on ``services/api``.
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://ignored:ignored@localhost:5432/ignored"
)
os.environ.setdefault("SESSION_SECRET", "test-secret-test-secret-test-secret!")
