"""H-04: verify the 0005 migration is well-formed.

Pure-logic — we read the Alembic revision script directly rather than running
Alembic against a real database. Mirrors the style used by
``tests/test_no_utcnow.py`` (filesystem sweep, no runtime side effects).
"""

from pathlib import Path

ALEMBIC_VERSIONS = (
    Path(__file__).resolve().parent.parent / "alembic" / "versions"
)


def _read_migration(name: str) -> str:
    path = ALEMBIC_VERSIONS / name
    return path.read_text(encoding="utf-8")


def test_0005_migration_file_exists():
    assert (ALEMBIC_VERSIONS / "0005_password_policy.py").is_file()


def test_0005_revision_identifiers_chain_correctly():
    src = _read_migration("0005_password_policy.py")
    assert 'revision: str = "0005"' in src, "0005 must declare its own revision id"
    assert 'down_revision: Union[str, None] = "0004"' in src, (
        "0005 must chain to the 0004 (auth rate-limit) migration"
    )


def test_0005_adds_both_password_policy_columns():
    src = _read_migration("0005_password_policy.py")
    assert "password_changed_at" in src, "0005 must add password_changed_at"
    assert "must_rotate_password" in src, "0005 must add must_rotate_password"


def test_0005_backfill_is_idempotent():
    """The ``WHERE must_rotate_password IS FALSE`` guard is what makes the
    backfill safe to re-run across branches."""
    src = _read_migration("0005_password_policy.py")
    assert "must_rotate_password IS FALSE" in src, (
        "seed-email backfill must be guarded so repeated runs don't loop"
    )


def test_0005_has_matching_downgrade():
    src = _read_migration("0005_password_policy.py")
    assert 'drop_column("users", "must_rotate_password")' in src
    assert 'drop_column("users", "password_changed_at")' in src
