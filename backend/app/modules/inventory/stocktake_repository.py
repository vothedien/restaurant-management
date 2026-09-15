from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.inventory import StockLot, StockMovement, Stocktake, StocktakeItem


class StocktakeRepository:
    @staticmethod
    def get(session: Session, stocktake_id: int, *, lock: bool = False) -> Stocktake | None:
        query = select(Stocktake).where(Stocktake.stocktake_id == stocktake_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return session.scalar(query)

    @staticmethod
    def items(session: Session, stocktake_id: int) -> list[StocktakeItem]:
        return list(
            session.scalars(
                select(StocktakeItem)
                .where(StocktakeItem.stocktake_id == stocktake_id)
                .order_by(StocktakeItem.stocktake_item_id)
                .execution_options(populate_existing=True)
            )
        )

    @staticmethod
    def list(
        session: Session, *, status: str | None, limit: int, offset: int
    ) -> tuple[list[Stocktake], int]:
        query = select(Stocktake)
        if status is not None:
            query = query.where(Stocktake.status == status)
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = session.scalars(
            query.order_by(Stocktake.stocktake_id.desc()).limit(limit).offset(offset)
        )
        return list(rows), total

    @staticmethod
    def lots(session: Session, lot_ids: list[int], *, lock: bool = False) -> list[StockLot]:
        query = (
            select(StockLot)
            .where(StockLot.stock_lot_id.in_(lot_ids))
            .order_by(StockLot.stock_lot_id)
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return list(session.scalars(query))

    @staticmethod
    def has_movements_since(session: Session, lot_ids: list[int], started_at: datetime) -> bool:
        return (
            session.scalar(
                select(StockMovement.stock_movement_id)
                .where(
                    StockMovement.stock_lot_id.in_(lot_ids),
                    StockMovement.occurred_at >= started_at,
                )
                .limit(1)
            )
            is not None
        )
