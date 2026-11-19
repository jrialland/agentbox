import { Link, Outlet, useNavigate } from "react-router-dom";

import { useAuthStore } from "../../store/auth";
import { ProjectTree } from "../projects/ProjectTree";

export function AppShell() {
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);
  const navigate = useNavigate();
  const canAdmin =
    user?.permissions.includes("roles:manage") ||
    user?.permissions.includes("users:manage");
  const canApiKeys = user?.permissions.includes("api_keys:manage");

  function logout() {
    clear();
    navigate("/login");
  }

  return (
    <div>
      <nav className="navbar" role="navigation" aria-label="main navigation">
        <div className="navbar-brand">
          <Link className="navbar-item" to="/">
            Agentbox
          </Link>
        </div>
        <div className="navbar-menu is-active">
          <div className="navbar-start">
            <Link className="navbar-item" to="/agents">
              Agents
            </Link>
            <Link className="navbar-item" to="/providers">
              Providers
            </Link>
            {canAdmin && (
              <Link className="navbar-item" to="/admin">
                Admin
              </Link>
            )}
            {canApiKeys && (
              <Link className="navbar-item" to="/api-keys">
                API keys
              </Link>
            )}
          </div>
          <div className="navbar-end">
            <span className="navbar-item">{user?.username}</span>
            <div className="navbar-item">
              <button className="button is-light" onClick={logout} type="button">
                Logout
              </button>
            </div>
          </div>
        </div>
      </nav>
      <div className="columns">
        <aside className="column is-2">
          <ProjectTree />
        </aside>
        <main className="column">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
