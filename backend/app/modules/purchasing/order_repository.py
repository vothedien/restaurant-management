from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.catalog import Ingredient, Unit
from app.db.models.inventory import (
    GoodsReceipt,
    GoodsReceiptItem,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
    SupplierIngredient,
)


class PurchaseOrderRepository:
    @staticmethod
    def get(session: Session, order_id: int, *, lock: bool = False) -> PurchaseOrder | None:
        query = select(PurchaseOrder).where(PurchaseOrder.purchase_order_id == order_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return session.scalar(query)

    @staticmethod
    def items(session: Session, order_id: int) -> list[PurchaseOrderItem]:
        return list(
            session.scalars(
                select(PurchaseOrderItem)
                .where(
                    PurchaseOrderItem.purchase_order_id == order_id,
                )
                .order_by(PurchaseOrderItem.purchase_order_item_id)
            )
        )

    @staticmethod
    def list(
        session: Session,
        *,
        supplier_id: int | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[PurchaseOrder], int]:
        query = select(PurchaseOrder)
        if supplier_id is not None:
            query = query.where(PurchaseOrder.supplier_id == supplier_id)
        if status is not None:
            query = query.where(PurchaseOrder.status == status)
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        orders = session.scalars(
            query.order_by(
                PurchaseOrder.purchase_order_id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(orders), total

    @staticmethod
    def supplier(session: Session, supplier_id: int) -> Supplier | None:
        return session.scalar(
            select(Supplier)
            .where(
                Supplier.supplier_id == supplier_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    @staticmethod
    def mappings(session: Session, ids: list[int], *, lock: bool = False):
        query = (
            select(SupplierIngredient)
            .where(
                SupplierIngredient.supplier_ingredient_id.in_(ids),
            )
            .order_by(SupplierIngredient.supplier_ingredient_id)
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return {row.supplier_ingredient_id: row for row in session.scalars(query)}

    @staticmethod
    def unit(session: Session, unit_id: int) -> Unit | None:
        return session.get(Unit, unit_id)

    @staticmethod
    def ingredient(session: Session, ingredient_id: int) -> Ingredient | None:
        return session.get(Ingredient, ingredient_id)

    @staticmethod
    def received_quantities(session: Session, order_id: int) -> dict[int, Decimal]:
        query = (
            select(
                GoodsReceiptItem.purchase_order_item_id,
                func.sum(GoodsReceiptItem.received_quantity),
            )
            .join(GoodsReceipt)
            .where(
                GoodsReceipt.purchase_order_id == order_id,
                GoodsReceipt.status == "CONFIRMED",
            )
            .group_by(GoodsReceiptItem.purchase_order_item_id)
        )
        return dict(session.execute(query).all())

    @staticmethod
    def has_receipts(session: Session, order_id: int, *, confirmed_only: bool = False) -> bool:
        query = select(GoodsReceipt.goods_receipt_id).where(
            GoodsReceipt.purchase_order_id == order_id,
        )
        if confirmed_only:
            query = query.where(GoodsReceipt.status == "CONFIRMED")
        return session.scalar(query.limit(1)) is not None
