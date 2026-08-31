# Code ownership

## Person 1 — Inventory

- `backend/app/modules/inventory`
- `backend/app/modules/purchasing`
- `backend/app/modules/forecasting`
- `frontend/src/features/inventory`
- Inventory and forecasting models

## Person 2 — Sales App

- `backend/app/modules/auth`
- `backend/app/modules/catalog`
- `backend/app/modules/sales`
- `frontend/src/features/auth`
- `frontend/src/features/sales`
- RBAC, catalog, and sales models

## Shared code

- `backend/app/core`
- `backend/app/db/session.py`
- `backend/app/api`
- `frontend/src/api`
- `frontend/src/components`
- `database`
- Alembic configuration

Change shared code only after both contributors agree. One person owns migrations and is the only person permitted to run them against Neon.

Do not push directly to `main`. Use `develop`, `feature/inventory`, and `feature/sales-app`; merge to `develop` through a Pull Request.
