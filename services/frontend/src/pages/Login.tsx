import { useState } from "react";
import { api } from "../api/client";

export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setMessage(null);
    try {
      const user = await api.login(username, password);
      setMessage(`Signed in as ${user.email} (${user.role})`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "login failed");
    }
  }

  return (
    <form onSubmit={onSubmit} style={{ display: "grid", gap: 8, maxWidth: 320 }}>
      <h1>Login</h1>
      <label>
        Email
        <input type="email" value={username} onChange={(e) => setUsername(e.target.value)} required />
      </label>
      <label>
        Password
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
      </label>
      <button type="submit">Sign in</button>
      {message && <p>{message}</p>}
    </form>
  );
}
