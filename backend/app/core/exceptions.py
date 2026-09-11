class DatabaseNotConfiguredError(RuntimeError):
    """Raised when an endpoint requires a database but DATABASE_URL is absent."""


class ApplicationError(Exception):
    """Expected application error that can be returned safely to an API client."""

    status_code = 400

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class BusinessRuleError(ApplicationError):
    """Raised when otherwise valid input violates a business rule."""


class NotFoundError(ApplicationError):
    """Raised when a requested resource does not exist."""

    status_code = 404


class ConflictError(ApplicationError):
    """Raised when a unique resource already exists."""

    status_code = 409
