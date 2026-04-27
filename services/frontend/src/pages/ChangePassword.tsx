import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";

export default function ChangePassword() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const user = auth.status === "authenticated" ? auth.user : null;
  const forced = user?.must_rotate_password ?? false;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setInfo(null);
    if (next !== confirm) {
      setError("New password and confirmation do not match");
      return;
    }
    setSubmitting(true);
    try {
      await api.changeMyPassword(current, next);
      await auth.refresh();
      setInfo("Password updated.");
      setCurrent("");
      setNext("");
      setConfirm("");
      if (forced) navigate("/dashboard", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) setError(err.detail);
      else setError("Password change failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <h1>Change password</h1>
      {forced && (
        <div className="error" role="alert">
          Your password must be rotated before you can continue using Chronos.
        </div>
      )}
      <div className="card" style={{ maxWidth: 480 }}>
        <form className="form" onSubmit={onSubmit}>
          <label>
            Current password
            <input
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
            />
          </label>
          <label>
            New password
            <input
              type="password"
              autoComplete="new-password"
              minLength={12}
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
            />
          </label>
          <label>
            Confirm new password
            <input
              type="password"
              autoComplete="new-password"
              minLength={12}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
            />
          </label>
          <p className="muted">
            At least 12 characters and include an uppercase letter, a lowercase
            letter, a digit, and a special character. Must not contain common
            words like your email or "password".
          </p>
          <button type="submit" disabled={submitting}>
            {submitting ? "Updating…" : "Update password"}
          </button>
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          {info && (
            <div className="info" role="status">
              {info}
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
