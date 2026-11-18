import { type FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { useAuthStore } from "../store/auth";

export function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const setToken = useAuthStore((s) => s.setToken);
  const setUser = useAuthStore((s) => s.setUser);
  const from =
    (location.state as { from?: { pathname: string } } | null)?.from?.pathname ?? "/";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const res = await api.POST("/auth/login", { body: { username, password } });
    if (res.error) {
      setError("Invalid credentials");
      return;
    }
    setToken(res.data.access_token);
    const me = await api.GET("/auth/me");
    if (me.data) setUser(me.data);
    navigate(from, { replace: true });
  }

  return (
    <div className="container">
      <h1 className="title">Login</h1>
      {error && <div className="notification is-danger">{error}</div>}
      <form onSubmit={onSubmit}>
        <div className="field">
          <label className="label" htmlFor="username">
            Username
          </label>
          <input
            id="username"
            className="input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>
        <div className="field">
          <label className="label" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            className="input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <button className="button is-primary" type="submit">
          Log in
        </button>
      </form>
    </div>
  );
}
