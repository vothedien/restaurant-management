# Code ownership

## Person 1 — Sales App

- `backend/app/modules/auth`, `backend/app/modules/catalog`, and `backend/app/modules/sales`
- RBAC, catalog, and sales models
- `frontend/src/features/auth` and `frontend/src/features/sales`
- Shared frontend layout, router, and sidebar

## Person 2 — Inventory

- Database models, Alembic, migrations, and backend integration
- `backend/app/modules/inventory`, `backend/app/modules/purchasing`, `backend/app/modules/forecasting`, and recipes
- `frontend/src/features/inventory` and purchasing features

Person 2 is the only contributor permitted to manage or run migrations against Neon. AI model training and evaluation are shared future work.

Do not push directly to `main`. Develop each feature on its own branch and merge to `develop` through a Pull Request.
