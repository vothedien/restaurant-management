from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.modules.inventory_auth.dependencies import (
    InventoryActor,
    require_inventory_permission,
)
from app.modules.inventory_auth.service import PURCHASE_READ_PERMISSIONS
from app.modules.purchasing.receipt_schemas import GoodsReceiptCreate, ReceiptStatus
from app.modules.purchasing.receipt_service import GoodsReceiptService
from app.modules.purchasing.schemas import MAX_BIGINT

router = APIRouter(prefix="/goods-receipts", tags=["goods receipts"])
service = GoodsReceiptService()
Db = Annotated[Session, Depends(get_db)]
ReceiptId = Annotated[int, Path(gt=0, le=MAX_BIGINT)]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_inventory_permission("INVENTORY_MANAGE"))],
)
def create_receipt(data: GoodsReceiptCreate, session: Db, actor: InventoryActor) -> dict:
    data = data.model_copy(update={"received_by": actor.user_id})
    result = service.create(session, data)
    return success_response("Goods receipt created", result.model_dump(mode="json"))


@router.get("", dependencies=[Depends(require_inventory_permission(*PURCHASE_READ_PERMISSIONS))])
def list_receipts(
    session: Db,
    purchase_order_id: int | None = Query(default=None, gt=0, le=MAX_BIGINT),
    status_filter: Annotated[ReceiptStatus | None, Query(alias="status")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    items, total = service.list(
        session,
        purchase_order_id=purchase_order_id,
        status=status_filter,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return success_response(
        "Goods receipts retrieved",
        {
            "items": [item.model_dump(mode="json") for item in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get(
    "/{receipt_id}",
    dependencies=[Depends(require_inventory_permission(*PURCHASE_READ_PERMISSIONS))],
)
def get_receipt(receipt_id: ReceiptId, session: Db) -> dict:
    return success_response(
        "Goods receipt retrieved",
        service.get(
            session,
            receipt_id,
        ).model_dump(mode="json"),
    )


@router.post(
    "/{receipt_id}/confirm",
    dependencies=[Depends(require_inventory_permission("INVENTORY_MANAGE"))],
)
def confirm_receipt(receipt_id: ReceiptId, session: Db, actor: InventoryActor) -> dict:
    result = service.confirm(session, receipt_id, performed_by=actor.user_id)
    return success_response("Goods receipt confirmed", result.model_dump(mode="json"))


@router.post(
    "/{receipt_id}/cancel", dependencies=[Depends(require_inventory_permission("INVENTORY_MANAGE"))]
)
def cancel_receipt(receipt_id: ReceiptId, session: Db) -> dict:
    result = service.cancel(session, receipt_id)
    return success_response("Goods receipt cancelled", result.model_dump(mode="json"))
