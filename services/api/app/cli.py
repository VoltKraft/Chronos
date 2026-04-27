"""CLI utilities for the Chronos API.

Run inside the container, e.g.:
    docker compose -f compose.dev.yaml --env-file .env.dev exec api \\
        python -m app.cli create-admin --email admin@chronos.local
"""

import argparse
import inspect
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from getpass import getpass
from pathlib import Path

from fastapi.params import Depends as DependsMarker
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Department, LeaveRequest, Preference, Project, Shift, Team, User
from app.models.enums import LeaveStatus, LeaveType, PreferenceType, Role, ShiftType
from app.security import hash_password, validate_password_strength
from app.services import audit

log = logging.getLogger(__name__)


def _cmd_create_admin(args: argparse.Namespace) -> int:
    email = args.email.strip().lower()
    password = args.password or getpass("Password: ")
    if not password:
        print("password is required", file=sys.stderr)
        return 2

    # H-04: enforce the policy on new admin credentials unless the operator
    # explicitly opts out (e.g. one-off rescue flows).
    try:
        validate_password_strength(password, skip_policy=bool(args.skip_policy))
    except ValueError as exc:
        print(f"password rejected: {exc}", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.email == email))
        if existing is not None:
            print(f"user already exists: {email}", file=sys.stderr)
            return 1
        user = User(
            email=email,
            password_hash=hash_password(password),
            first_name=args.first_name,
            last_name=args.last_name,
            role=Role.admin.value,
            password_changed_at=datetime.now(timezone.utc),
            must_rotate_password=False,
        )
        db.add(user)
        db.commit()
        print(f"created admin {email} (id={user.id})")
    return 0


def _cmd_seed_demo(args: argparse.Namespace) -> int:
    """Load a small but realistic dataset for development / demos."""
    today = date.today()

    # H-04: the seed intentionally plants weak passwords to keep the docs and
    # muscle-memory short. Bypass the policy explicitly, flag every seeded
    # account for forced rotation, and shout about it so the operator never
    # ships these defaults.
    validate_password_strength("admin", skip_policy=True)
    log.warning(
        "seed-demo planted weak default passwords; every seeded user is flagged "
        "with must_rotate_password=True and must rotate before anything real"
    )
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == "admin@chronos.local")) is None:
            admin = User(
                email="admin@chronos.local",
                password_hash=hash_password("admin-pass-1"),
                first_name="Sys",
                last_name="Admin",
                role=Role.admin.value,
                password_changed_at=now,
                must_rotate_password=True,
            )
            db.add(admin)
            db.flush()
            print(f"admin seeded (password: admin-pass-1)")
        else:
            admin = db.scalar(select(User).where(User.email == "admin@chronos.local"))

        if db.scalar(select(Department)) is not None:
            print("demo data already present, skipping")
            return 0

        dep = Department(name="Operations")
        db.add(dep)
        db.flush()
        team = Team(name="Support", department_id=dep.id)
        db.add(team)
        db.flush()
        project = Project(code="CUST-01", name="Customer Service")
        db.add(project)
        db.flush()

        people: dict[str, User] = {}
        roster = [
            ("hr@chronos.local", "Helena", "Ross", Role.hr),
            ("lead@chronos.local", "Lea", "Durand", Role.team_lead),
            ("alice@chronos.local", "Alice", "Nowak", Role.employee),
            ("bob@chronos.local", "Bob", "Weber", Role.employee),
            ("carol@chronos.local", "Carol", "Meier", Role.employee),
            ("dan@chronos.local", "Dan", "Klein", Role.employee),
        ]
        for email, first, last, role in roster:
            u = User(
                email=email,
                password_hash=hash_password("demo-pass-1"),
                first_name=first,
                last_name=last,
                role=role.value,
                department_id=dep.id,
                team_id=team.id if role != Role.hr else None,
                password_changed_at=now,
                must_rotate_password=True,
            )
            db.add(u)
            db.flush()
            people[email] = u

        # Preferences
        db.add(
            Preference(
                user_id=people["alice@chronos.local"].id,
                preference_type=PreferenceType.shift_time.value,
                payload={"preferred": ShiftType.early.value},
                effective_from=today - timedelta(days=30),
            )
        )
        db.add(
            Preference(
                user_id=people["bob@chronos.local"].id,
                preference_type=PreferenceType.shift_time.value,
                payload={"preferred": ShiftType.late.value},
                effective_from=today - timedelta(days=30),
            )
        )
        db.add(
            Preference(
                user_id=people["carol@chronos.local"].id,
                preference_type=PreferenceType.day_off.value,
                payload={"weekdays": [4]},
                effective_from=today - timedelta(days=30),
            )
        )

        # Pending leave request
        leave = LeaveRequest(
            requester_id=people["alice@chronos.local"].id,
            approver_delegate_id=people["bob@chronos.local"].id,
            approver_tl_id=people["lead@chronos.local"].id,
            approver_hr_id=people["hr@chronos.local"].id,
            type=LeaveType.vacation.value,
            start_date=today + timedelta(days=14),
            end_date=today + timedelta(days=18),
            status=LeaveStatus.draft.value,
            reason="Summer break",
        )
        db.add(leave)
        db.commit()
        print("seeded: 1 department, 1 team, 1 project, 6 users, 3 preferences, 1 leave draft")
    return 0


def _cmd_verify_audit(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        ok, checked, bad = audit.verify_chain(db)
        print(json.dumps({"ok": ok, "checked": checked, "first_bad_id": bad}, indent=2))
    return 0 if ok else 1


def _cmd_dump_openapi(args: argparse.Namespace) -> int:
    """Write the FastAPI-generated OpenAPI spec to disk.

    The FS requires the OpenAPI document to be the contract source of truth
    (`docs/api/openapi/<service>/openapi.yaml`). This command regenerates it so
    CI can diff-check the committed copy against the live FastAPI app.
    """
    from app.main import app  # imported here to keep CLI startup lean

    spec = app.openapi()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.format == "json" or output.suffix.lower() == ".json":
        output.write_text(json.dumps(spec, indent=2, sort_keys=False) + "\n")
    else:
        try:
            import yaml  # type: ignore
        except ImportError:
            print(
                "PyYAML is not installed; install it or pass --format json",
                file=sys.stderr,
            )
            return 2
        output.write_text(yaml.safe_dump(spec, sort_keys=False))
    print(f"wrote {output} ({len(spec.get('paths', {}))} paths)")
    return 0


_ROUTE_MATRIX_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def _route_matrix_guards(fn) -> list[str]:
    """Return the RBAC-relevant dependency names from ``fn``'s signature.

    Walks ``inspect.signature(fn)`` looking at parameter defaults that are
    ``fastapi.params.Depends`` markers, and pulls the dependency callable's
    ``__name__``. That surfaces ``current_user`` and every ``require_*``
    factory (which rebrand themselves via ``_dep.__name__`` in
    ``app.permissions.require_roles``), so the audit matrix shows exactly
    which guard each endpoint runs behind.
    """
    guards: list[str] = []
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return guards
    for param in sig.parameters.values():
        default = param.default
        if isinstance(default, DependsMarker) and default.dependency is not None:
            name = getattr(default.dependency, "__name__", None)
            if name:
                guards.append(name)
    return guards


def _cmd_dump_route_matrix(args: argparse.Namespace) -> int:
    """Emit a method × path × guard matrix for every registered route.

    Phase-1 security hardening relies on a manual audit of RBAC coverage.
    This command dumps the same shape reviewers build by hand: one row per
    (method, path), listing the dependency callables that guard the handler
    (``current_user``, ``require_hr_or_admin``, …). Output is JSON by default
    or a Markdown table when ``--format markdown`` is passed; either can be
    diffed in CI or pasted into a PR.
    """
    from fastapi.routing import APIRoute

    from app.main import app

    rows: list[dict[str, object]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods or set()):
            if method not in _ROUTE_MATRIX_HTTP_METHODS:
                continue
            rows.append(
                {
                    "method": method,
                    "path": route.path,
                    "guards": _route_matrix_guards(route.endpoint),
                    "module": getattr(route.endpoint, "__module__", ""),
                    "name": getattr(route.endpoint, "__qualname__", ""),
                }
            )
    rows.sort(key=lambda r: (str(r["path"]), str(r["method"])))

    output_path = Path(args.output) if args.output else None

    if args.format == "markdown":
        lines = ["| Method | Path | Guards | Handler |", "| --- | --- | --- | --- |"]
        for row in rows:
            guards = ", ".join(str(g) for g in row["guards"]) or "—"
            handler = f"{row['module']}:{row['name']}"
            lines.append(f"| {row['method']} | `{row['path']}` | {guards} | `{handler}` |")
        text = "\n".join(lines) + "\n"
    else:
        text = json.dumps(rows, indent=2, sort_keys=False) + "\n"

    if output_path is None:
        sys.stdout.write(text)
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text)
        print(f"wrote {output_path} ({len(rows)} routes)")
    return 0


def _cmd_set_role(args: argparse.Namespace) -> int:
    email = args.email.strip().lower()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            print(f"no such user: {email}", file=sys.stderr)
            return 1
        user.role = Role(args.role).value
        db.commit()
        print(f"role of {email} set to {user.role}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    admin = sub.add_parser("create-admin", help="Create an admin user")
    admin.add_argument("--email", required=True)
    admin.add_argument("--password", help="Omit to be prompted interactively")
    admin.add_argument("--first-name", dest="first_name")
    admin.add_argument("--last-name", dest="last_name")
    admin.add_argument(
        "--skip-policy",
        dest="skip_policy",
        action="store_true",
        help="Bypass the H-04 password strength policy (dangerous — only for rescue flows)",
    )
    admin.set_defaults(func=_cmd_create_admin, skip_policy=False)

    seed = sub.add_parser("seed-demo", help="Load a demo dataset")
    seed.set_defaults(func=_cmd_seed_demo)

    verify = sub.add_parser("verify-audit", help="Recompute and verify the audit hash chain")
    verify.set_defaults(func=_cmd_verify_audit)

    role = sub.add_parser("set-role", help="Change a user's role")
    role.add_argument("--email", required=True)
    role.add_argument("--role", required=True, choices=[r.value for r in Role])
    role.set_defaults(func=_cmd_set_role)

    openapi = sub.add_parser("dump-openapi", help="Dump the FastAPI OpenAPI document")
    openapi.add_argument(
        "--output",
        default="docs/api/openapi/api/openapi.yaml",
        help="Target path (default: docs/api/openapi/api/openapi.yaml)",
    )
    openapi.add_argument(
        "--format",
        choices=("yaml", "json"),
        default="yaml",
        help="Output format (default: inferred from file extension, else yaml)",
    )
    openapi.set_defaults(func=_cmd_dump_openapi)

    matrix = sub.add_parser(
        "dump-route-matrix",
        help="Dump method × path × guard matrix for every registered route",
    )
    matrix.add_argument(
        "--output",
        default=None,
        help="Target path (default: write to stdout)",
    )
    matrix.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format (default: json)",
    )
    matrix.set_defaults(func=_cmd_dump_route_matrix)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
