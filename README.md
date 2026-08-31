# Restaurant Management

Starter platform for a restaurant-management graduation project: sales operations, inventory, purchasing, demand forecasting, and replenishment proposals. It is a modular monolith with one FastAPI backend, one React frontend, and one existing Neon PostgreSQL database.

## Architecture

- Backend: Python 3.11+, FastAPI, synchronous SQLAlchemy 2.x, psycopg 3, Pydantic Settings, Alembic, Pytest, Ruff, and Uvicorn.
- Frontend: React, TypeScript, Vite, React Router, Axios, and ESLint.
- Database: the existing Neon PostgreSQL schema `restaurant_ai`. Its 33 tables are mapped by the backend; the application never calls `create_all`, runs the seed SQL, or migrates automatically.

## Structure

```text
restaurant-management/
├── database/                         # Source DDL; do not edit here
├── backend/
│   ├── app/core/                     # Settings, errors, response helpers
│   ├── app/db/models/                # 33 SQLAlchemy mappings
│   ├── app/modules/                  # auth, catalog, sales, inventory, purchasing, forecasting
│   ├── app/api/                      # v1 router
│   ├── alembic/                      # Future-only migration configuration
│   └── tests/
├── frontend/src/                     # React application
└── AGENTS.md                         # Team ownership rules
```

## Prerequisites

Install Python 3.11 or newer (ensure `py` or `python` is on PATH), Node.js 20+ with npm, and Git. This project has no Docker setup.

## Backend on Windows PowerShell

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend/.env` locally. Set `DATABASE_URL` to the Neon connection string for the existing database, keeping `sslmode=require`. Never commit this file.

In the Neon console, open the project, select **Connect**, choose the connection string for your application, and paste it only into `backend/.env`. Invite a teammate from the Neon project’s **Members** or **Settings** area with the least permission they need; do not share one account or an `.env` file.

Run the API:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Open Swagger at `http://localhost:8000/docs`. Health checks are `GET /health` and `GET /health/database`. The latter safely reports an unavailable configuration or connection and never returns a connection string.

Run verification:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
ruff check .
ruff format --check .
pytest
python scripts/check_database.py
```

Only run `check_database.py` after a valid local `.env` is present. It issues read-only checks and expects exactly 33 tables.

## Frontend on Windows PowerShell

```powershell
cd frontend
Copy-Item .env.example .env
npm.cmd install
npm.cmd run dev
```

`VITE_API_URL` defaults to `http://localhost:8000`; it must not contain secrets. Verify the frontend with:

```powershell
cd frontend
npm.cmd run lint
npm.cmd run build
```

## Database and Alembic policy

The 33 `restaurant_ai` tables already exist on Neon. Do not generate an initial migration for them and do not run `alembic upgrade`, `stamp`, `downgrade`, or autogeneration against Neon without the team’s explicit agreement. Alembic is configured only for future schema changes, and one designated person manages migrations.

## Collaboration and Git

Use `develop` as the integration branch and `feature/inventory` or `feature/sales-app` for work. Submit a Pull Request to merge into `develop`; never push directly to `main`.

Invite team members to GitHub from the repository’s **Settings → Collaborators** (or the organization team) with appropriate permissions. Protect `main` and `develop` with PR review checks when a remote repository is added. No remote is configured by this starter project.

## Security

`.env`, virtual environments, Node modules, build output, IDE settings, caches, and test artifacts are ignored. Review `git status` before every commit and never commit Neon passwords, API secrets, or real connection strings.
