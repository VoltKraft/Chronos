"""Route-introspection tests for H-01: /api/workflows mutating endpoints
must require HR or admin; read endpoints stay open to any authenticated user.
"""

from fastapi.routing import APIRoute

from app.main import app


def _dep_names(route: APIRoute) -> set[str]:
    return {d.call.__name__ for d in route.dependant.dependencies if d.call is not None}


def _find(path: str, method: str) -> APIRoute:
    for r in app.routes:
        if isinstance(r, APIRoute) and r.path == path and method in r.methods:
            return r
    raise AssertionError(f"no route {method} {path}")


def test_workflows_list_is_open_to_any_user():
    route = _find("/api/workflows", "GET")
    names = _dep_names(route)
    assert "current_user" in names
    assert "require_roles_admin_hr" not in names


def test_workflows_create_requires_hr_or_admin():
    route = _find("/api/workflows", "POST")
    assert "require_roles_admin_hr" in _dep_names(route)


def test_workflows_update_requires_hr_or_admin():
    route = _find("/api/workflows/{workflow_id}", "PUT")
    assert "require_roles_admin_hr" in _dep_names(route)


def test_workflows_delete_requires_hr_or_admin():
    route = _find("/api/workflows/{workflow_id}", "DELETE")
    assert "require_roles_admin_hr" in _dep_names(route)
