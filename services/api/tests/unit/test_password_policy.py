"""H-04: unit tests for the password strength validator.

All checks are pure-logic — the function operates on a string and either
returns ``None`` or raises ``ValueError`` with a rule-identifying message.
"""

import pytest

from app.security import PASSWORD_MIN_LENGTH, validate_password_strength


def test_accepts_a_strong_password():
    # Hits every required class: lower, upper, digit, special; no blocklist word.
    validate_password_strength("Str0ng-PassPhrase!")


@pytest.mark.parametrize(
    ("raw", "needle"),
    [
        ("Aa1!xyz", "too short"),  # length < 12
        ("SHORT1!DIGIT", "lowercase"),  # no lower
        ("nouppercase1!extra", "uppercase"),  # no upper
        ("NoDigitHere!!extra", "digit"),  # no digit
        ("NoSpecialHere12345", "special"),  # no special char
    ],
)
def test_rejects_when_a_single_class_is_missing(raw: str, needle: str):
    with pytest.raises(ValueError) as exc:
        validate_password_strength(raw)
    assert needle in str(exc.value).lower()


@pytest.mark.parametrize(
    "raw",
    [
        "Password12345!",       # exact lowercase hit on 'password'
        "somePASSWORDthing1!",  # embedded hit, case-insensitive
        "Ch4ng3Me!Chronos!",    # hits 'chronos'
        "MyWelcome9!pack",      # hits 'welcome'
        "QWERTYuiop12!",        # hits 'qwerty' via case-fold
    ],
)
def test_rejects_blocklist_substrings(raw: str):
    with pytest.raises(ValueError) as exc:
        validate_password_strength(raw)
    assert "blocklist" in str(exc.value).lower()


def test_skip_policy_disables_all_checks():
    # Obviously weak — would fail length, class, and blocklist rules — but the
    # bypass is explicit and returns ``None``.
    validate_password_strength("admin", skip_policy=True)


def test_minimum_length_is_documented_constant():
    # Guard so we don't silently drop the bar below 12 in a later change.
    assert PASSWORD_MIN_LENGTH >= 12


def test_error_message_mentions_min_length_constant():
    with pytest.raises(ValueError) as exc:
        validate_password_strength("Aa1!")
    assert str(PASSWORD_MIN_LENGTH) in str(exc.value)
