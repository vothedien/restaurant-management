from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    success: bool = True
    message: str
    data: Any


def success_response(message: str, data: Any) -> dict[str, Any]:
    return {"success": True, "message": message, "data": data}
