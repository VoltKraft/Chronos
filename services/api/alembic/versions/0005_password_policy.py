"""password policy: password_changed_at + must_rotate_password on users

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-20

Adds two columns supporting H-04 forced-rotation + password-policy enforcement:

* ``password_changed_at`` — audit timestamp of the last successful rotation.
* ``must_rotate_password`` — signals to the UI that the user has to pick a new
  password on the next login. Seed-demo fixture accounts are forced to rotate
  so weak defaults never survive bootstrap.

Backfill is idempotent: it scopes updates with ``WHERE must_rotate_password IS
FALSE`` so re-running the migration (or running it twice across branches)
never double-applies the fixture flag.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Seed-demo fixture emails: any match forces a rotate on first login.
_SEED_EMAILS: tuple[str, ...] = (
    "admin@chronos.local",
    "hr@chronos.local",
    "tl@chronos.local",
)
# Employees are created as employee*@chronos.local by the seed helper (and by
# the older fixture list — alice/bob/carol/dan). Matching by LIKE catches both.
_SEED_EMPLOYEE_LIKE: str = "employee%@chronos.local"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "password_changed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "must_rotate_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Backfill: stamp existing rows with now() so we don't immediately flag
    # every historical user as "must rotate".
    op.execute(
        sa.text(
            "UPDATE users SET password_changed_at = now() "
            "WHERE password_changed_at IS NULL"
        )
    )

    # Flip must_rotate_password for seed fixtures only; idempotent via the
    # FALSE guard so re-runs are safe.
    op.execute(
        sa.text(
            """
            UPDATE users
            SET must_rotate_password = TRUE
            WHERE must_rotate_password IS FALSE
              AND (
                email IN ('admin@chronos.local', 'hr@chronos.local', 'tl@chronos.local')
                OR email LIKE 'employee%@chronos.local'
              )
            """
        )
    )


def downgrade() -> None:
    op.drop_column("users", "must_rotate_password")
    op.drop_column("users", "password_changed_at")
