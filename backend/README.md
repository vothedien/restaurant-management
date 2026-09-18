# Backend

Inventory now has independent bcrypt/JWT authentication backed by the existing
RBAC tables. Configure the separate Inventory secret and read
[Inventory Auth](docs/inventory-auth.md) before using protected Inventory,
purchasing or recipe APIs. No production accounts or schema are created.

Run commands from this directory after creating a Python 3.11+ virtual environment and installing `requirements.txt`.

`app/db/models` contains mappings for the 33 existing tables in Neon schema `restaurant_ai`; no table is created at application startup. `GET /health` works without a database. `GET /health/database` and `scripts/check_database.py` are read-only connection checks.

Use Alembic only for future, agreed schema changes. Do not create or run an initial migration for the existing 33 tables.

Purchase orders, goods receipts, stock lookup/FEFO issues, stocktakes, and the
inventory service for completed order items are documented in
[Inventory workflows (Vietnamese)](docs/inventory-workflows.md), including the
offline demo, transaction rules, API payloads and remaining Sales integration.

Run the full offline suite with `python -m pytest`, then `ruff check .` and
`ruff format --check .`. Tests disable dotenv/database configuration and create
only isolated SQLite fixtures; they do not connect to Neon. PostgreSQL lock SQL
is checked, but actual concurrent locking needs a separate PostgreSQL test database.
