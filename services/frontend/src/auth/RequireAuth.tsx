import { Navigate, useLocation } from "react-router-dom";
import { hasRole, useAuth } from "./AuthProvider";
import type { Role } from "../api/client";

const CHANGE_PASSWORD_PATH = "/change-password";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const auth = useAuth();
  const location = useLocation();
  if (auth.status === "loading") return <div className="pending">Loading…</div>;
  if (auth.status !== "authenticated") {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  if (auth.user.must_rotate_password && location.pathname !== CHANGE_PASSWORD_PATH) {
    return <Navigate to={CHANGE_PASSWORD_PATH} replace />;
  }
  return <>{children}</>;
}

export function RequireRole({ roles, children }: { roles: Role[]; children: React.ReactNode }) {
  const auth = useAuth();
  const location = useLocation();
  if (auth.status === "loading") return <div className="pending">Loading…</div>;
  if (auth.status !== "authenticated") return <Navigate to="/login" replace />;
  if (auth.user.must_rotate_password && location.pathname !== CHANGE_PASSWORD_PATH) {
    return <Navigate to={CHANGE_PASSWORD_PATH} replace />;
  }
  if (!hasRole(auth.user, ...roles)) {
    return (
      <div className="error-panel" role="alert">
        <h2>Access denied</h2>
        <p>Your role ({auth.user.role}) does not grant access to this page.</p>
      </div>
    );
  }
  return <>{children}</>;
}
