"""H-07 — every mutating config endpoint must call audit.append.

Pure source-introspection so we don't need a DB. Adds a guard that future
edits don't silently drop the audit hook.
"""
from __future__ import annotations

import inspect

from app.routers import delegates as delegates_router
from app.routers import users as users_router


def _source_of(fn) -> str:
    return inspect.getsource(fn)


def test_users_update_user_audits_changes():
    src = _source_of(users_router.update_user)
    assert "audit.append" in src
    assert "AuditAction.config_change" in src
    assert 'target_type="user"' in src


def test_delegates_create_audits():
    src = _source_of(delegates_router.create_delegate)
    assert "audit.append" in src
    assert "AuditAction.config_change" in src
    assert 'target_type="delegate"' in src


def test_delegates_delete_audits():
    src = _source_of(delegates_router.delete_delegate)
    assert "audit.append" in src
    assert "AuditAction.config_change" in src
    assert 'target_type="delegate"' in src


def test_users_set_role_audits():
    # Pre-existing but covered so a regression is caught here too.
    src = _source_of(users_router.set_role)
    assert "audit.append" in src
    assert "AuditAction.role_change" in src


def test_users_deactivate_audits():
    src = _source_of(users_router.deactivate)
    assert "audit.append" in src
    assert "AuditAction.data_erase" in src
