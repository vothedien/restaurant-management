from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.modules.inventory.stocktake_schemas import (
    StocktakeComplete,
    StocktakeCount,
    StocktakeCreate,
    StocktakeStart,
    StocktakeStatus,
)
from app.modules.inventory.stocktake_service import StocktakeService
from app.modules.purchasing.schemas import MAX_BIGINT

router = APIRouter(prefix="/stocktakes", tags=["stocktakes"])
service = StocktakeService()
Db = Annotated[Session, Depends(get_db)]
ResourceId = Annotated[int, Path(gt=0, le=MAX_BIGINT)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_stocktake(data: StocktakeCreate, session: Db) -> dict:
    result = service.create(session, data)
    return success_response("Stocktake created", result.model_dump(mode="json"))


@router.get("")
def list_stocktakes(
    session: Db,
    status_filter: Annotated[StocktakeStatus | None, Query(alias="status")] = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    items, total = service.list(session, status=status_filter, limit=limit, offset=offset)
    return success_response(
        "Stocktakes retrieved",
        {
            "items": [item.model_dump(mode="json") for item in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/{stocktake_id}")
def get_stocktake(stocktake_id: ResourceId, session: Db) -> dict:
    result = service.get(session, stocktake_id)
    return success_response("Stocktake retrieved", result.model_dump(mode="json"))


@router.post("/{stocktake_id}/start")
def start_stocktake(stocktake_id: ResourceId, data: StocktakeStart, session: Db) -> dict:
    result = service.start(session, stocktake_id, data)
    return success_response("Stocktake started", result.model_dump(mode="json"))


@router.patch("/{stocktake_id}/items/{item_id}")
def record_count(
    stocktake_id: ResourceId, item_id: ResourceId, data: StocktakeCount, session: Db
) -> dict:
    result = service.count(session, stocktake_id, item_id, data)
    return success_response("Stocktake count recorded", result.model_dump(mode="json"))


@router.post("/{stocktake_id}/complete")
def complete_stocktake(stocktake_id: ResourceId, data: StocktakeComplete, session: Db) -> dict:
    result = service.complete(session, stocktake_id, data)
    return success_response("Stocktake completed", result.model_dump(mode="json"))


@router.post("/{stocktake_id}/cancel")
def cancel_stocktake(stocktake_id: ResourceId, session: Db) -> dict:
    result = service.cancel(session, stocktake_id)
    return success_response("Stocktake cancelled", result.model_dump(mode="json"))
