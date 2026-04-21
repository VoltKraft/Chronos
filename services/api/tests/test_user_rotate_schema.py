"""H-04: the ``UserPublic`` schema must carry ``must_rotate_password``.

The SPA consumes ``UserPublic`` from ``/auth/me`` and ``/auth/login``; without
this field the frontend cannot tell whether a fresh session has to detour to
the change-password page.
"""

from app.routers.auth import UserPublic


def test_userpublic_declares_must_rotate_password_field():
    fields = UserPublic.model_fields
    assert "must_rotate_password" in fields, (
        "UserPublic must expose must_rotate_password for the H-04 rotate flow"
    )


def test_must_rotate_password_is_boolean():
    field = UserPublic.model_fields["must_rotate_password"]
    assert field.annotation is bool, f"expected bool, got {field.annotation!r}"


def test_must_rotate_password_defaults_to_false():
    # Backwards-compatible default so stored sessions from before H-04 still
    # deserialise cleanly.
    instance = UserPublic(
        id="00000000-0000-0000-0000-000000000001",
        email="noone@example.com",
        role="employee",
        locale="en",
        time_zone="UTC",
    )
    assert instance.must_rotate_password is False
