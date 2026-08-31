from fastapi import APIRouter

from app.core.responses import success_response

router = APIRouter(prefix="/purchasing", tags=["purchasing"])


@router.get("/status")
def purchasing_status() -> dict[str, object]:
    return success_response("Purchasing module scaffold is ready", {"implemented": False})
