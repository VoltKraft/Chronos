from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


# H-04: password-policy constants. Kept in-module so the CLI, the routers, and
# the tests all import from the same place.
PASSWORD_MIN_LENGTH = 12

# Case-insensitive substring blocklist. Any credential containing one of these
# as a lowercased substring is rejected outright so seed defaults like
# ``admin`` / ``changeme`` never ride into prod.
PASSWORD_BLOCKLIST: frozenset[str] = frozenset(
    {
        "password",
        "passw0rd",
        "chronos",
        "admin",
        "welcome",
        "letmein",
        "qwerty",
        "123456",
        "changeme",
    }
)

# The OWASP-suggested "printable special" ranges from ASCII 33–126 excluding
# letters and digits: !-/, :-@, [-`, {-~. Explicit character-class check keeps
# the rule documentable without pulling in a regex engine.
_SPECIAL_CHARS = frozenset(
    [chr(c) for c in range(0x21, 0x30)]  # !-/
    + [chr(c) for c in range(0x3A, 0x41)]  # :-@
    + [chr(c) for c in range(0x5B, 0x61)]  # [-`
    + [chr(c) for c in range(0x7B, 0x7F)]  # {-~
)


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False


def validate_password_strength(raw: str, *, skip_policy: bool = False) -> None:
    """Enforce the H-04 password policy.

    Rules (all must pass):

    * length >= ``PASSWORD_MIN_LENGTH``
    * contains at least one lowercase letter, one uppercase letter,
      one digit and one special character
    * does not contain any entry from ``PASSWORD_BLOCKLIST`` (case-insensitive
      substring match)

    Raises ``ValueError`` with a human-readable message pinpointing the
    failing rule. When ``skip_policy=True`` the function is a no-op and the
    caller is responsible for the consequences — used exclusively by the
    demo seed, which needs the historical weak defaults.
    """
    if skip_policy:
        return

    if not isinstance(raw, str):  # pragma: no cover - defensive
        raise ValueError("password must be a string")

    if len(raw) < PASSWORD_MIN_LENGTH:
        raise ValueError(
            f"password too short: at least {PASSWORD_MIN_LENGTH} characters required"
        )

    if not any(c.islower() for c in raw):
        raise ValueError("password must contain at least one lowercase letter")

    if not any(c.isupper() for c in raw):
        raise ValueError("password must contain at least one uppercase letter")

    if not any(c.isdigit() for c in raw):
        raise ValueError("password must contain at least one digit")

    if not any(c in _SPECIAL_CHARS for c in raw):
        raise ValueError("password must contain at least one special character")

    lowered = raw.lower()
    for needle in PASSWORD_BLOCKLIST:
        if needle in lowered:
            raise ValueError(
                f"password is on the blocklist: contains '{needle}'"
            )
