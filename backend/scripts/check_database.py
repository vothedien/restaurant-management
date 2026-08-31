"""Read-only Neon check; this script never runs migrations or seed data."""

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine

EXPECTED_TABLE_COUNT = 33


def main() -> None:
    settings = get_settings()
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))
        count = connection.scalar(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_type = 'BASE TABLE'"
            ),
            {"schema": settings.database_schema},
        )
    if count != EXPECTED_TABLE_COUNT:
        raise SystemExit(f"Expected {EXPECTED_TABLE_COUNT} tables; found {count}.")
    print(f"Database check passed: {count} tables in schema '{settings.database_schema}'.")


if __name__ == "__main__":
    main()
