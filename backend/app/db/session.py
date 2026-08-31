from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.exceptions import DatabaseNotConfiguredError

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _database_url_with_ssl() -> str:
    database_url = get_settings().database_url
    if not database_url:
        raise DatabaseNotConfiguredError("DATABASE_URL is not configured.")

    url = make_url(database_url)
    if url.drivername.startswith("postgresql") and "sslmode" not in url.query:
        url = url.update_query_dict({**url.query, "sslmode": "require"})
    return url.render_as_string(hide_password=False)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            _database_url_with_ssl(),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            pool_recycle=1800,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """Yield one synchronous database session per request and always close it."""

    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
