# Frontend

Install dependencies with `npm.cmd install`, copy `.env.example` to `.env`, and run `npm.cmd run dev` from this directory.

The app reads `VITE_API_URL` (default `http://localhost:8000`). Keep local environment files and credentials out of Git. Run `npm.cmd run lint`, `npm.cmd run typecheck`, `npm.cmd run test` and `npm.cmd run build` for verification.

## Inventory

Inventory has its own layout at `/inventory/*`, a public entry at `/inventory/login`, and no Sales links. Business routes require an authenticated session and suitable permissions before mounting their pages. The top bar shows the current user, roles and logout; the backend derives business actors from the authenticated user.

**Inventory Auth is implemented independently of Sales** at `/api/v1/inventory-auth/{login,me,logout,status}`, using the existing RBAC/audit tables. Configure the separate Inventory secret in the backend process; see [backend Auth](../backend/docs/inventory-auth.md). Login verifies bcrypt and issues an Inventory-only JWT; the frontend stores it in `sessionStorage.inventory_access_token`. Logout clears the client session; issued JWTs expire normally. No default production account or role picker is provided.

See [Inventory UI](docs/inventory-ui.md) for routes, business rules, decimals, reports and run instructions; [Auth integration](docs/inventory-auth-integration.md) for permissions, current-user attribution and the remaining Person 1 dependencies; [verification checkpoint](docs/inventory-ui-progress.md) for commands actually run and their results.

Browser tests (`npm.cmd run test:e2e`) use the explicit `e2e/vite.config.ts` frontend on port **5174** and the real Inventory Auth/business API backed by disposable SQLite on **8011**. The production adapter is used without an alias or mocked login/me. Follow the isolated setup in the Inventory guide; this does not verify production deployment, PostgreSQL concurrency or Neon.
