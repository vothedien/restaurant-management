class DatabaseNotConfiguredError(RuntimeError):
    """Raised when an endpoint requires a database but DATABASE_URL is absent."""
