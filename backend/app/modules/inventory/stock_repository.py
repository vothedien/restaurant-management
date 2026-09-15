from datetime import date, datetime

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.db.models.catalog import Ingredient, Unit, UnitConversion
from app.db.models.inventory import StockLot, StockMovement


class StockRepository:
    @staticmethod
    def eligible(today: date):
        return (
            (StockLot.status == "ACTIVE")
            & StockLot.ingredient_id.in_(
                select(Ingredient.ingredient_id).where(Ingredient.status == "ACTIVE")
            )
            & (StockLot.current_quantity > 0)
            & or_(StockLot.expiry_date.is_(None), StockLot.expiry_date >= today)
            & or_(StockLot.manufacture_date.is_(None), StockLot.manufacture_date <= today)
        )

    def lock_available_lots(self, session: Session, ingredient_ids: list[int], today: date):
        return list(
            session.scalars(
                select(StockLot)
                .where(StockLot.ingredient_id.in_(ingredient_ids), self.eligible(today))
                .order_by(StockLot.stock_lot_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )

    @staticmethod
    def get_lot(session: Session, lot_id: int, *, for_update: bool = False):
        statement = select(StockLot).where(StockLot.stock_lot_id == lot_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return session.scalar(statement)

    @staticmethod
    def get_unit(session: Session, unit_id: int):
        return session.get(Unit, unit_id)

    @staticmethod
    def get_conversion(session: Session, from_unit_id: int, to_unit_id: int):
        return session.scalar(
            select(UnitConversion).where(
                UnitConversion.from_unit_id == from_unit_id,
                UnitConversion.to_unit_id == to_unit_id,
            )
        )

    def balances(self, session: Session, *, ingredient_id: int | None, limit: int, offset: int):
        totals = (
            select(
                StockLot.ingredient_id,
                func.sum(StockLot.current_quantity).label("current_quantity"),
                func.sum(
                    case((self.eligible(date.today()), StockLot.current_quantity), else_=0)
                ).label("available_quantity"),
            )
            .group_by(StockLot.ingredient_id)
            .subquery()
        )
        conditions = [] if ingredient_id is None else [Ingredient.ingredient_id == ingredient_id]
        statement = (
            select(
                Ingredient,
                func.coalesce(totals.c.current_quantity, 0),
                func.coalesce(totals.c.available_quantity, 0),
            )
            .outerjoin(totals, Ingredient.ingredient_id == totals.c.ingredient_id)
            .where(*conditions)
            .order_by(Ingredient.ingredient_id)
            .limit(limit)
            .offset(offset)
        )
        total = session.scalar(select(func.count()).select_from(Ingredient).where(*conditions))
        return list(session.execute(statement)), int(total or 0)

    def list_lots(
        self,
        session: Session,
        *,
        ingredient_id: int | None,
        status: str | None,
        available_only: bool,
        limit: int,
        offset: int,
    ):
        conditions = []
        if ingredient_id is not None:
            conditions.append(StockLot.ingredient_id == ingredient_id)
        if status is not None:
            conditions.append(StockLot.status == status)
        if available_only:
            conditions.append(self.eligible(date.today()))
        rows = list(
            session.scalars(
                select(StockLot)
                .where(*conditions)
                .order_by(StockLot.stock_lot_id)
                .limit(limit)
                .offset(offset)
            )
        )
        total = session.scalar(select(func.count()).select_from(StockLot).where(*conditions))
        return rows, int(total or 0)

    @staticmethod
    def list_movements(
        session: Session,
        *,
        ingredient_id: int | None,
        stock_lot_id: int | None,
        movement_type: str | None,
        occurred_from: datetime | None,
        occurred_to: datetime | None,
        limit: int,
        offset: int,
    ):
        conditions = []
        if ingredient_id is not None:
            conditions.append(StockMovement.ingredient_id == ingredient_id)
        if stock_lot_id is not None:
            conditions.append(StockMovement.stock_lot_id == stock_lot_id)
        if movement_type is not None:
            conditions.append(StockMovement.movement_type == movement_type)
        if occurred_from is not None:
            conditions.append(StockMovement.occurred_at >= occurred_from)
        if occurred_to is not None:
            conditions.append(StockMovement.occurred_at <= occurred_to)
        rows = list(
            session.scalars(
                select(StockMovement)
                .where(*conditions)
                .order_by(StockMovement.occurred_at.desc(), StockMovement.stock_movement_id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        total = session.scalar(select(func.count()).select_from(StockMovement).where(*conditions))
        return rows, int(total or 0)
