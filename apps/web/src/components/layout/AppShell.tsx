import { Link, Outlet, useNavigate } from "react-router-dom";

import { useAuthStore } from "../../store/auth";

export function AppShell() {
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);
  const navigate = useNavigate();

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
          <aside className="menu">
            <p className="menu-label">Navigation</p>
            <ul className="menu-list">
              <li>
                <Link to="/agents">Agents</Link>
              </li>
              <li>
                <Link to="/providers">Providers</Link>
              </li>
              <li>
                <Link to="/projects">Projects</Link>
              </li>
            </ul>
          </aside>
        </aside>
        <main className="column">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
