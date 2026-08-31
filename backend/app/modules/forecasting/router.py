from fastapi import APIRouter

from app.core.responses import success_response

router = APIRouter(prefix="/forecasting", tags=["forecasting"])


@router.get("/status")
def forecasting_status() -> dict[str, object]:
    return success_response("Forecasting module scaffold is ready", {"implemented": False})
