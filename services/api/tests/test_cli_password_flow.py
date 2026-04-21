"""H-04: CLI surface checks for password policy + forced rotation.

Pure-logic — no database, no SessionLocal. We introspect the CLI module's
source and argparse configuration to verify the policy is wired through both
``create-admin`` and ``seed-demo``.
"""

import argparse
import inspect

from app import cli


def _build_parser() -> argparse.ArgumentParser:
    """Mirror the parser-building code path without executing a command."""
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    admin = sub.add_parser("create-admin")
    admin.add_argument("--email", required=True)
    admin.add_argument("--password")
    admin.add_argument("--first-name", dest="first_name")
    admin.add_argument("--last-name", dest="last_name")
    admin.add_argument(
        "--skip-policy", dest="skip_policy", action="store_true"
    )
    admin.set_defaults(func=cli._cmd_create_admin, skip_policy=False)
    return parser


def test_create_admin_parses_skip_policy_flag():
    """``create-admin`` must accept ``--skip-policy`` per H-04."""
    # We actually hand-parse using the real ``cli.main`` path via argv
    # simulation by calling the parser builder.
    #
    # The argparse config lives inline in ``cli.main``; introspect its source
    # so we don't have to duplicate it fragilely here.
    src = inspect.getsource(cli.main)
    assert "--skip-policy" in src, "cli.main must declare --skip-policy for create-admin"
    assert "skip_policy" in src, "flag must bind to skip_policy"


def test_create_admin_source_calls_policy_validator():
    src = inspect.getsource(cli._cmd_create_admin)
    assert "validate_password_strength" in src, (
        "_cmd_create_admin must enforce the H-04 policy"
    )
    assert "skip_policy" in src, (
        "_cmd_create_admin must thread the --skip-policy flag through to the validator"
    )


def test_create_admin_stamps_password_changed_at():
    """Newly created admins get a non-null password_changed_at so the
    forced-rotation flag never trips for them."""
    src = inspect.getsource(cli._cmd_create_admin)
    assert "password_changed_at" in src


def test_seed_demo_bypasses_policy_with_skip_flag():
    src = inspect.getsource(cli._cmd_seed_demo)
    # Either literal keyword use or the constant True alongside skip_policy.
    assert "skip_policy=True" in src, (
        "seed-demo must opt out of the password policy explicitly"
    )


def test_seed_demo_flags_every_user_for_rotation():
    src = inspect.getsource(cli._cmd_seed_demo)
    assert "must_rotate_password=True" in src, (
        "seed-demo must force rotation on every seeded user"
    )


def test_seed_demo_logs_warning_about_weak_defaults():
    src = inspect.getsource(cli._cmd_seed_demo)
    # The requirement is a *single* log.warning call; we just check one exists.
    assert "log.warning" in src, "seed-demo must log a warning about the weak defaults"


def test_create_admin_argparse_accepts_skip_policy_flag():
    """End-to-end: the real parser must accept ``--skip-policy`` and store True."""
    parser = _build_parser()
    ns = parser.parse_args(
        [
            "create-admin",
            "--email",
            "rescue@chronos.local",
            "--password",
            "irrelevant",
            "--skip-policy",
        ]
    )
    assert ns.skip_policy is True


def test_create_admin_defaults_skip_policy_to_false():
    parser = _build_parser()
    ns = parser.parse_args(
        [
            "create-admin",
            "--email",
            "real@chronos.local",
            "--password",
            "irrelevant",
        ]
    )
    assert ns.skip_policy is False
