from fastapi import HTTPException, status


def authentication_not_implemented() -> HTTPException:
    """Temporary placeholder until the authentication module is implemented."""

    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Authentication is not implemented yet.",
    )
