from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.db.models.inventory import StockLot, Stocktake, StocktakeItem
from app.modules.inventory.stock_common import (
    add_movement,
    database_errors,
    lock_ingredients,
    require_actor,
    stock_now,
    transaction,
)
from app.modules.inventory.stock_service import StockService
from app.modules.inventory.stocktake_repository import StocktakeRepository
from app.modules.inventory.stocktake_schemas import (
    StocktakeComplete,
    StocktakeCount,
    StocktakeCreate,
    StocktakeDetail,
    StocktakeItemRead,
    StocktakeRead,
    StocktakeStart,
)


class StocktakeService:
    def __init__(self, repository: StocktakeRepository | None = None):
        self.repository = repository or StocktakeRepository()

    def create(self, session: Session, data: StocktakeCreate) -> StocktakeDetail:
        with transaction(session):
            require_actor(session, data.created_by)
            stocktake = Stocktake(
                stocktake_number=data.stocktake_number or f"STK-{uuid4().hex}",
                created_by=data.created_by,
                notes=data.notes,
                status="DRAFT",
            )
            session.add(stocktake)
            session.flush()
            result = self._detail(session, stocktake)
        return result

    def list(self, session: Session, **filters) -> tuple[list[StocktakeRead], int]:
        with database_errors(session):
            rows, total = self.repository.list(session, **filters)
            return [StocktakeRead.model_validate(row) for row in rows], total

    def get(self, session: Session, stocktake_id: int) -> StocktakeDetail:
        with database_errors(session):
            return self._detail(session, self._require(session, stocktake_id))

    def start(self, session: Session, stocktake_id: int, data: StocktakeStart) -> StocktakeDetail:
        with transaction(session):
            stocktake = self._require(session, stocktake_id, lock=True)
            if stocktake.status != "DRAFT":
                raise ConflictError("Only draft stocktakes can be started")
            lots = self._lock_lots(session, data.stock_lot_ids)
            stocktake.started_at = stock_now(session)
            stocktake.status = "IN_PROGRESS"
            for lot in lots.values():
                session.add(
                    StocktakeItem(
                        stocktake_id=stocktake_id,
                        stock_lot_id=lot.stock_lot_id,
                        system_quantity=lot.current_quantity,
                        actual_quantity=lot.current_quantity,
                        adjustment_reason=None,
                    )
                )
            session.flush()
            result = self._detail(session, stocktake)
        return result

    def count(
        self, session: Session, stocktake_id: int, item_id: int, data: StocktakeCount
    ) -> StocktakeDetail:
        with transaction(session):
            stocktake = self._require(session, stocktake_id, lock=True)
            self._require_in_progress(stocktake)
            items = self.repository.items(session, stocktake_id)
            item = next((row for row in items if row.stocktake_item_id == item_id), None)
            if item is None:
                raise NotFoundError("Stocktake item not found")
            lots = self._lock_lots(session, [row.stock_lot_id for row in items])
            self._validate_snapshot(session, stocktake, items, lots)
            StockService.validate_count(lots[item.stock_lot_id], data.actual_quantity)
            item.actual_quantity = data.actual_quantity
            item.adjustment_reason = data.adjustment_reason
            session.flush()
            result = self._detail(session, stocktake)
        return result

    def complete(
        self, session: Session, stocktake_id: int, data: StocktakeComplete
    ) -> StocktakeDetail:
        with transaction(session):
            stocktake = self._require(session, stocktake_id, lock=True)
            # The source lock serializes competing submissions. Returning the
            # stored result preserves actor/timestamp and creates no new movement.
            if stocktake.status == "COMPLETED":
                result = self._detail(session, stocktake)
            else:
                self._require_in_progress(stocktake)
                require_actor(session, data.completed_by)
                items = self.repository.items(session, stocktake_id)
                if not items or any(not row.adjustment_reason for row in items):
                    raise ConflictError(
                        "Every stocktake item must have an explicitly recorded count"
                    )
                lots = self._lock_lots(session, [row.stock_lot_id for row in items])
                self._validate_snapshot(session, stocktake, items, lots)
                # Validate the complete plan before applying any stock changes.
                for item in items:
                    StockService.validate_count(lots[item.stock_lot_id], item.actual_quantity)
                for item in items:
                    variance = item.actual_quantity - item.system_quantity
                    if variance == 0:
                        continue
                    lot = lots[item.stock_lot_id]
                    lot.current_quantity = item.actual_quantity
                    StockService.refresh_lot_status(lot)
                    add_movement(
                        session,
                        lot,
                        movement_type="ADJUSTMENT",
                        direction="IN" if variance > 0 else "OUT",
                        quantity=abs(variance),
                        performed_by=data.completed_by,
                        stocktake_item_id=item.stocktake_item_id,
                        reason=item.adjustment_reason,
                    )
                stocktake.status = "COMPLETED"
                stocktake.completed_at = stock_now(session)
                stocktake.completed_by = data.completed_by
                session.flush()
                result = self._detail(session, stocktake)
        return result

    def cancel(self, session: Session, stocktake_id: int) -> StocktakeDetail:
        with transaction(session):
            stocktake = self._require(session, stocktake_id, lock=True)
            if stocktake.status == "COMPLETED":
                raise ConflictError("Completed stocktakes cannot be cancelled")
            stocktake.status = "CANCELLED"
            session.flush()
            result = self._detail(session, stocktake)
        return result

    def _lock_lots(self, session: Session, lot_ids: list[int]) -> dict[int, StockLot]:
        initial = self.repository.lots(session, lot_ids)
        if len(initial) != len(set(lot_ids)):
            raise NotFoundError("Stock lot not found")
        # All writers acquire ingredient locks before lot locks, in ascending ID
        # order. Count corrections may inspect inactive ingredients/blocked lots.
        lock_ingredients(session, [row.ingredient_id for row in initial], active=False)
        lots = self.repository.lots(session, lot_ids, lock=True)
        if len(lots) != len(set(lot_ids)):
            raise NotFoundError("Stock lot not found")
        return {lot.stock_lot_id: lot for lot in lots}

    def _validate_snapshot(
        self,
        session: Session,
        stocktake: Stocktake,
        items: list[StocktakeItem],
        lots: dict[int, StockLot],
    ) -> None:
        if stocktake.started_at is None:
            raise ConflictError("Stocktake has no start snapshot")
        if any(lots[item.stock_lot_id].current_quantity != item.system_quantity for item in items):
            raise ConflictError(
                "Stock changed after counting started; cancel and start a new stocktake"
            )
        # Compare ledger activity too: an issue followed by a return can leave
        # the same quantity but invalidates the physical-count window.
        if self.repository.has_movements_since(session, list(lots), stocktake.started_at):
            raise ConflictError(
                "Stock moved after counting started; cancel and start a new stocktake"
            )

    def _require(self, session: Session, stocktake_id: int, *, lock: bool = False) -> Stocktake:
        stocktake = self.repository.get(session, stocktake_id, lock=lock)
        if stocktake is None:
            raise NotFoundError("Stocktake not found")
        return stocktake

    @staticmethod
    def _require_in_progress(stocktake: Stocktake) -> None:
        if stocktake.status != "IN_PROGRESS":
            raise ConflictError("Only in-progress stocktakes can be counted or completed")

    def _detail(self, session: Session, stocktake: Stocktake) -> StocktakeDetail:
        items = [
            StocktakeItemRead(
                stocktake_item_id=item.stocktake_item_id,
                stocktake_id=item.stocktake_id,
                stock_lot_id=item.stock_lot_id,
                system_quantity=item.system_quantity,
                actual_quantity=item.actual_quantity,
                variance_quantity=item.variance_quantity,
                adjustment_reason=item.adjustment_reason,
                counted=bool(item.adjustment_reason),
            )
            for item in self.repository.items(session, stocktake.stocktake_id)
        ]
        return StocktakeDetail(**StocktakeRead.model_validate(stocktake).model_dump(), items=items)
