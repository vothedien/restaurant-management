from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.modules.inventory.stock_schemas import LotStatus, MovementType, StockAdjustment, StockIssue
from app.modules.inventory.stock_service import StockService
from app.modules.inventory_auth.dependencies import (
    InventoryActor,
    require_inventory_permission,
)
from app.modules.inventory_auth.service import STOCK_READ_PERMISSIONS

router = APIRouter(tags=["stock"])
service = StockService()
ResourceId = Annotated[int, Path(gt=0, le=9223372036854775807)]
Db = Annotated[Session, Depends(get_db)]


def page(message, rows, total, limit, offset):
    return success_response(
        message,
        {
            "items": [r.model_dump(mode="json") for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/stock", dependencies=[Depends(require_inventory_permission(*STOCK_READ_PERMISSIONS))])
def balances(
    session: Db,
    ingredient_id: int | None = Query(None, gt=0, le=9223372036854775807),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    rows, total = service.list_balances(
        session, ingredient_id=ingredient_id, limit=limit, offset=offset
    )
    return page("Stock balances retrieved", rows, total, limit, offset)


@router.get(
    "/stock-lots", dependencies=[Depends(require_inventory_permission(*STOCK_READ_PERMISSIONS))]
)
def lots(
    session: Db,
    ingredient_id: int | None = Query(None, gt=0, le=9223372036854775807),
    status: LotStatus | None = None,
    available_only: bool = False,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    rows, total = service.list_lots(
        session,
        ingredient_id=ingredient_id,
        status=status,
        available_only=available_only,
        limit=limit,
        offset=offset,
    )
    return page("Stock lots retrieved", rows, total, limit, offset)


@router.get(
    "/stock-lots/{lot_id}",
    dependencies=[Depends(require_inventory_permission(*STOCK_READ_PERMISSIONS))],
)
def lot(lot_id: ResourceId, session: Db):
    return success_response(
        "Stock lot retrieved", service.get_lot(session, lot_id).model_dump(mode="json")
    )


@router.get(
    "/stock-movements",
    dependencies=[Depends(require_inventory_permission(*STOCK_READ_PERMISSIONS))],
)
def movements(
    session: Db,
    ingredient_id: int | None = Query(None, gt=0, le=9223372036854775807),
    stock_lot_id: int | None = Query(None, gt=0, le=9223372036854775807),
    movement_type: MovementType | None = None,
    occurred_from: AwareDatetime | None = None,
    occurred_to: AwareDatetime | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    rows, total = service.list_movements(
        session,
        ingredient_id=ingredient_id,
        stock_lot_id=stock_lot_id,
        movement_type=movement_type,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        limit=limit,
        offset=offset,
    )
    return page("Stock movements retrieved", rows, total, limit, offset)


@router.post(
    "/stock/issues",
    status_code=201,
    dependencies=[Depends(require_inventory_permission("INVENTORY_MANAGE"))],
)
def issue(data: StockIssue, session: Db, actor: InventoryActor):
    data = data.model_copy(update={"performed_by": actor.user_id})
    return success_response("Stock issued", service.issue(session, data).model_dump(mode="json"))


@router.post(
    "/stock-lots/{lot_id}/adjust",
    dependencies=[Depends(require_inventory_permission("INVENTORY_MANAGE"))],
)
def adjust(lot_id: ResourceId, data: StockAdjustment, session: Db, actor: InventoryActor):
    data = data.model_copy(update={"performed_by": actor.user_id})
    return success_response(
        "Stock adjusted", service.adjust(session, lot_id, data).model_dump(mode="json")
    )
