import { NavLink, Outlet } from "react-router-dom";

import { DatabaseStatus } from "../components/DatabaseStatus";

export function MainLayout() {
  return (
    <div className="app-shell">
      <header className="header">
        <NavLink className="brand" to="/">Restaurant Management</NavLink>
        <nav aria-label="Main navigation">
          <NavLink to="/sales">Sales</NavLink>
          <NavLink to="/inventory">Inventory</NavLink>
          <NavLink to="/login">Login</NavLink>
        </nav>
      </header>
      <main className="content">
        <DatabaseStatus />
        <Outlet />
      </main>
    </div>
  );
}
