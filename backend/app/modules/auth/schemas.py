from pydantic import BaseModel


class LoginPlaceholder(BaseModel):
    message: str = "Authentication will be implemented in this module."
