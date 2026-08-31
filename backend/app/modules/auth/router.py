from fastapi import APIRouter

from app.core.responses import success_response

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/status")
def auth_status() -> dict[str, object]:
    return success_response("Authentication module scaffold is ready", {"implemented": False})
