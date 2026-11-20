import { type FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { Button } from "../design-system/primitives/Button";
import { InlineError } from "../design-system/forms/InlineError";
import { FormField } from "../design-system/forms/FormField";
import { PasswordInput } from "../design-system/forms/PasswordInput";
import { TextInput } from "../design-system/forms/TextInput";
import { AuthCard } from "../design-system/patterns/AuthCard";
import { useAuthStore } from "../store/auth";
import styles from "./login.module.css";

export function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const setToken = useAuthStore((s) => s.setToken);
  const setUser = useAuthStore((s) => s.setUser);
  const from =
    (location.state as { from?: { pathname: string } } | null)?.from
      ?.pathname ?? "/";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      const res = await api.POST("/auth/login", {
        body: { username, password },
      });
      if (res.error) {
        setError("Invalid credentials");
        return;
      }
      setToken(res.data.access_token);
      const me = await api.GET("/auth/me");
      if (me.data) setUser(me.data);
      navigate(from, { replace: true });
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthCard title="Login" subtitle="Authenticate to open the console.">
      <form className={styles.form} onSubmit={onSubmit}>
        {error && <InlineError>{error}</InlineError>}
        <FormField label="Username" htmlFor="username" required>
          <TextInput
            id="username"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.currentTarget.value)}
          />
        </FormField>
        <FormField label="Password" htmlFor="password" required>
          <PasswordInput
            id="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.currentTarget.value)}
          />
        </FormField>
        <Button type="submit" loading={pending}>
          Log in
        </Button>
      </form>
    </AuthCard>
  );
}
