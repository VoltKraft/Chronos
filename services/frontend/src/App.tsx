import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth, isHrOrAdmin, isTlOrAbove } from "./auth/AuthProvider";

type NavItem = { to: string; label: string; show: boolean };

export default function App() {
  const auth = useAuth();
  const navigate = useNavigate();
  const user = auth.status === "authenticated" ? auth.user : null;
  const mustRotate = user?.must_rotate_password ?? false;

  const items: NavItem[] = [
    { to: "/dashboard", label: "Dashboard", show: !!user && !mustRotate },
    { to: "/leave", label: "My leave", show: !!user && !mustRotate },
    { to: "/leave/new", label: "Request leave", show: !!user && !mustRotate },
    { to: "/inbox", label: "Approvals", show: !!user && !mustRotate },
    { to: "/shifts", label: "Shifts", show: !!user && !mustRotate },
    { to: "/preferences", label: "Preferences", show: !!user && !mustRotate },
    { to: "/planner", label: "Planner", show: isTlOrAbove(user) && !mustRotate },
    { to: "/reports", label: "Reports", show: isTlOrAbove(user) && !mustRotate },
    { to: "/users", label: "Users", show: isHrOrAdmin(user) && !mustRotate },
    { to: "/audit", label: "Audit", show: isHrOrAdmin(user) && !mustRotate },
    { to: "/workflows", label: "Workflows", show: isHrOrAdmin(user) && !mustRotate },
  ];

  const handleLogout = async () => {
    await auth.logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand">
          <strong>Chronos</strong>
          <span className="brand-sub">Shift & leave planning</span>
        </div>
        {user && (
          <nav className="main-nav" aria-label="Primary">
            {items
              .filter((it) => it.show)
              .map((it) => (
                <NavLink
                  key={it.to}
                  to={it.to}
                  className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
                >
                  {it.label}
                </NavLink>
              ))}
          </nav>
        )}
        <div className="user-pill">
          {user ? (
            <>
              <span className="user-email">{user.email}</span>
              <span className="user-role">{user.role}</span>
              <NavLink to="/change-password" className="nav-link">
                Change password
              </NavLink>
              <button className="link-button" onClick={handleLogout}>
                Sign out
              </button>
            </>
          ) : (
            <NavLink to="/login" className="nav-link">
              Sign in
            </NavLink>
          )}
        </div>
      </header>
      <main className="app-main" id="main">
        <Outlet />
      </main>
      <footer className="app-footer">
        <small>Chronos Phase 1 — © Chronos contributors · AGPL-3.0-only</small>
      </footer>
    </div>
  );
}
