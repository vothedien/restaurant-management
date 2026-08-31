# Backend

Run commands from this directory after creating a Python 3.11+ virtual environment and installing `requirements.txt`.

`app/db/models` contains mappings for the 33 existing tables in Neon schema `restaurant_ai`; no table is created at application startup. `GET /health` works without a database. `GET /health/database` and `scripts/check_database.py` are read-only connection checks.

Use Alembic only for future, agreed schema changes. Do not create or run an initial migration for the existing 33 tables.
