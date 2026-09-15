from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.modules.purchasing.order_schemas import (
    PurchaseOrderCreate,
    PurchaseOrderStatus,
    PurchaseOrderTransition,
    PurchaseOrderUpdate,
)
from app.modules.purchasing.order_service import PurchaseOrderService
from app.modules.purchasing.schemas import MAX_BIGINT

router = APIRouter(prefix="/purchase-orders", tags=["purchase orders"])
service = PurchaseOrderService()
Db = Annotated[Session, Depends(get_db)]
OrderId = Annotated[int, Path(gt=0, le=MAX_BIGINT)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_order(data: PurchaseOrderCreate, session: Db) -> dict:
    result = service.create(session, data)
    return success_response("Purchase order created", result.model_dump(mode="json"))


@router.get("")
def list_orders(
    session: Db,
    supplier_id: int | None = Query(default=None, gt=0, le=MAX_BIGINT),
    status_filter: Annotated[PurchaseOrderStatus | None, Query(alias="status")] = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    items, total = service.list(
        session, supplier_id=supplier_id, status=status_filter, limit=limit, offset=offset
    )
    return success_response(
        "Purchase orders retrieved",
        {
            "items": [item.model_dump(mode="json") for item in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/{order_id}")
def get_order(order_id: OrderId, session: Db) -> dict:
    return success_response(
        "Purchase order retrieved",
        service.get(
            session,
            order_id,
        ).model_dump(mode="json"),
    )


@router.patch("/{order_id}")
def update_order(order_id: OrderId, data: PurchaseOrderUpdate, session: Db) -> dict:
    result = service.update(session, order_id, data)
    return success_response("Purchase order updated", result.model_dump(mode="json"))


@router.post("/{order_id}/status")
def transition_order(order_id: OrderId, data: PurchaseOrderTransition, session: Db) -> dict:
    result = service.transition(session, order_id, data)
    return success_response("Purchase order status updated", result.model_dump(mode="json"))
