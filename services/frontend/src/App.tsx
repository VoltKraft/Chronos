import { Link, Outlet } from "react-router-dom";

export default function App() {
  return (
    <div style={{ fontFamily: "system-ui, sans-serif" }}>
      <header style={{ padding: "12px 20px", borderBottom: "1px solid #ddd", display: "flex", gap: 16 }}>
        <strong>Chronos</strong>
        <nav style={{ display: "flex", gap: 12 }}>
          <Link to="/workflows">Workflows</Link>
          <Link to="/login">Login</Link>
        </nav>
      </header>
      <main style={{ padding: 20 }}>
        <Outlet />
      </main>
    </div>
  );
}
