"""H-08: forbid ``datetime.utcnow`` anywhere in the API package.

``datetime.utcnow`` is deprecated in Python 3.12 and returns a naive UTC value
that silently compares wrong against aware datetimes. Use
``datetime.now(timezone.utc)`` instead.
"""

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent.parent / "app"


def test_no_datetime_utcnow_in_app_tree():
    offenders = []
    for path in APP_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "datetime.utcnow" in line and not line.lstrip().startswith("#"):
                offenders.append(f"{path.relative_to(APP_ROOT.parent)}:{lineno}: {line.strip()}")
    assert not offenders, "datetime.utcnow() usages remain:\n" + "\n".join(offenders)
