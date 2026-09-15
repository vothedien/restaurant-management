from __future__ import annotations

from datetime import date

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.models.inventory import GoodsReceipt, GoodsReceiptItem, StockLot


class GoodsReceiptRepository:
    @staticmethod
    def order_id(session: Session, receipt_id: int) -> int | None:
        # Read only the immutable FK before locking the parent purchase order.
        return session.scalar(
            select(GoodsReceipt.purchase_order_id).where(
                GoodsReceipt.goods_receipt_id == receipt_id,
            )
        )

    @staticmethod
    def get(session: Session, receipt_id: int, *, lock: bool = False) -> GoodsReceipt | None:
        query = select(GoodsReceipt).where(GoodsReceipt.goods_receipt_id == receipt_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return session.scalar(query)

    @staticmethod
    def items(session: Session, receipt_id: int) -> list[GoodsReceiptItem]:
        return list(
            session.scalars(
                select(GoodsReceiptItem)
                .where(
                    GoodsReceiptItem.goods_receipt_id == receipt_id,
                )
                .order_by(GoodsReceiptItem.goods_receipt_item_id)
            )
        )

    @staticmethod
    def list(
        session: Session,
        *,
        purchase_order_id: int | None,
        status: str | None,
        date_from: date | None,
        date_to: date | None,
        limit: int,
        offset: int,
    ) -> tuple[list[GoodsReceipt], int]:
        query = select(GoodsReceipt)
        if purchase_order_id is not None:
            query = query.where(GoodsReceipt.purchase_order_id == purchase_order_id)
        if status is not None:
            query = query.where(GoodsReceipt.status == status)
        if date_from is not None:
            query = query.where(GoodsReceipt.receipt_date >= date_from)
        if date_to is not None:
            query = query.where(GoodsReceipt.receipt_date <= date_to)
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        receipts = session.scalars(
            query.order_by(
                GoodsReceipt.goods_receipt_id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(receipts), total

    @staticmethod
    def existing_lots(session: Session, keys: set[tuple[int, str]]) -> list[StockLot]:
        if not keys:
            return []
        query = (
            select(StockLot)
            .where(
                or_(
                    *(
                        and_(StockLot.ingredient_id == ingredient_id, StockLot.lot_code == lot_code)
                        for ingredient_id, lot_code in sorted(keys)
                    ),
                )
            )
            .order_by(StockLot.ingredient_id, StockLot.stock_lot_id)
        )
        return list(
            session.scalars(query.with_for_update().execution_options(populate_existing=True))
        )
