from fastapi import APIRouter

from app.core.responses import success_response

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/status")
def catalog_status() -> dict[str, object]:
    return success_response("Catalog module scaffold is ready", {"implemented": False})
