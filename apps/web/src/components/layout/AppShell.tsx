import { Link, Outlet } from "react-router-dom";

export function AppShell() {
  return (
    <div>
      <nav className="navbar" role="navigation" aria-label="main navigation">
        <div className="navbar-brand">
          <Link className="navbar-item" to="/">
            Agentbox
          </Link>
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
