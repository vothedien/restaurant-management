from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.db.models.inventory import StockLot, StockMovement
from app.modules.inventory.stock_common import (
    add_movement,
    database_errors,
    exact_quantity,
    lock_ingredients,
    require_actor,
    transaction,
)
from app.modules.inventory.stock_repository import StockRepository
from app.modules.inventory.stock_schemas import (
    StockAdjustment,
    StockBalanceRead,
    StockChangeRead,
    StockIssue,
    StockLotRead,
    StockMovementRead,
)


class StockService:
    def __init__(self, repository: StockRepository | None = None):
        self.repository = repository or StockRepository()

    def list_balances(self, session: Session, **filters):
        with database_errors(session):
            rows, total = self.repository.balances(session, **filters)
            return [
                StockBalanceRead(
                    ingredient_id=ingredient.ingredient_id,
                    ingredient_code=ingredient.ingredient_code,
                    ingredient_name=ingredient.ingredient_name,
                    base_unit_id=ingredient.base_unit_id,
                    current_quantity=current,
                    available_quantity=available,
                    unavailable_quantity=current - available,
                )
                for ingredient, current, available in rows
            ], total

    def list_lots(self, session: Session, **filters):
        with database_errors(session):
            rows, total = self.repository.list_lots(session, **filters)
            return [StockLotRead.model_validate(row) for row in rows], total

    def get_lot(self, session: Session, lot_id: int):
        with database_errors(session):
            return StockLotRead.model_validate(self._require_lot(session, lot_id))

    def list_movements(self, session: Session, **filters):
        with database_errors(session):
            start, end = filters.get("occurred_from"), filters.get("occurred_to")
            if start and end and end < start:
                raise BusinessRuleError("occurred_to must be on or after occurred_from")
            rows, total = self.repository.list_movements(session, **filters)
            return [StockMovementRead.model_validate(row) for row in rows], total

    def issue(self, session: Session, data: StockIssue):
        with transaction(session):
            ingredient = lock_ingredients(session, [data.ingredient_id])[data.ingredient_id]
            quantity = self.to_base(session, data.quantity, data.unit_id, ingredient.base_unit_id)
            movements = self.consume(
                session,
                {data.ingredient_id: quantity},
                performed_by=data.performed_by,
                reason=data.reason,
                movement_type="ADJUSTMENT",
            )
            session.flush()
            result = StockChangeRead(
                movements=[StockMovementRead.model_validate(m) for m in movements]
            )
        return result

    def adjust(self, session: Session, lot_id: int, data: StockAdjustment):
        with transaction(session):
            require_actor(session, data.performed_by)
            initial = self._require_lot(session, lot_id)
            lock_ingredients(session, [initial.ingredient_id], active=False)
            lot = self._require_lot(session, lot_id, for_update=True)
            variance = exact_quantity(data.actual_quantity - lot.current_quantity)
            self.validate_count(lot, data.actual_quantity)
            movements = []
            if variance:
                lot.current_quantity = data.actual_quantity
                self.refresh_lot_status(lot)
                movements.append(
                    add_movement(
                        session,
                        lot,
                        movement_type="ADJUSTMENT",
                        direction="IN" if variance > 0 else "OUT",
                        quantity=abs(variance),
                        performed_by=data.performed_by,
                        reason=data.reason,
                    )
                )
            session.flush()
            result = StockChangeRead(
                movements=[StockMovementRead.model_validate(m) for m in movements]
            )
        return result

    def consume(
        self,
        session: Session,
        requirements: dict[int, Decimal],
        *,
        performed_by: int | None,
        order_item_id: int | None = None,
        reason: str | None = None,
        movement_type: str = "CONSUMPTION",
    ) -> list[StockMovement]:
        """Plan all FEFO allocations, then apply; caller owns the transaction.

        Every stock writer locks ingredients ascending before locking lots. Row
        locks last until the outer transaction commits, including empty stock.
        """
        require_actor(session, performed_by)
        if not requirements:
            raise BusinessRuleError("At least one ingredient requirement is required")
        for quantity in requirements.values():
            if exact_quantity(quantity) <= 0:
                raise BusinessRuleError("Required quantities must be positive")
        lock_ingredients(session, requirements)
        lots = self.repository.lock_available_lots(session, sorted(requirements), date.today())
        # Unknown expiry comes last; receipt creation/id breaks ties deterministically.
        lots.sort(key=lambda lot: (lot.expiry_date or date.max, lot.created_at, lot.stock_lot_id))
        plan = []
        for ingredient_id, quantity in sorted(requirements.items()):
            remaining = quantity
            for lot in lots:
                if lot.ingredient_id != ingredient_id:
                    continue
                allocation = min(remaining, lot.current_quantity)
                if allocation > 0:
                    plan.append((lot, allocation))
                    remaining -= allocation
                if remaining == 0:
                    break
            if remaining > 0:
                raise ConflictError(f"Insufficient available stock for ingredient {ingredient_id}")
        movements = []
        for lot, quantity in plan:
            lot.current_quantity -= quantity
            self.refresh_lot_status(lot)
            movements.append(
                add_movement(
                    session,
                    lot,
                    movement_type=movement_type,
                    direction="OUT",
                    quantity=quantity,
                    performed_by=performed_by,
                    order_item_id=order_item_id,
                    reason=reason,
                )
            )
        session.flush()
        return movements

    def to_base(
        self, session: Session, quantity: Decimal, from_unit_id: int, base_unit_id: int
    ) -> Decimal:
        source = self.repository.get_unit(session, from_unit_id)
        target = self.repository.get_unit(session, base_unit_id)
        if source is None or target is None:
            raise NotFoundError("Unit not found")
        if not source.is_active or not target.is_active:
            raise BusinessRuleError("Units must be active")
        if from_unit_id == base_unit_id:
            return exact_quantity(quantity)
        if source.dimension != target.dimension:
            raise BusinessRuleError("Unit conversions require matching dimensions")
        conversion = self.repository.get_conversion(session, from_unit_id, base_unit_id)
        if conversion is None:
            raise BusinessRuleError("A direct conversion to the ingredient base unit is required")
        return exact_quantity(quantity * conversion.factor)

    def _require_lot(self, session: Session, lot_id: int, *, for_update: bool = False):
        lot = self.repository.get_lot(session, lot_id, for_update=for_update)
        if lot is None:
            raise NotFoundError("Stock lot not found")
        return lot

    @staticmethod
    def validate_count(lot: StockLot, quantity: Decimal):
        if exact_quantity(quantity) < 0:
            raise BusinessRuleError("Actual quantity cannot be negative")
        if quantity > lot.received_quantity:
            raise ConflictError(
                "Actual quantity exceeds the lot's original received quantity; "
                "a schema change is required for this surplus"
            )

    @staticmethod
    def refresh_lot_status(lot: StockLot):
        # Never unblock quarantined or explicitly expired lots during an adjustment.
        if lot.status in {"ACTIVE", "DEPLETED"}:
            lot.status = "DEPLETED" if lot.current_quantity == 0 else "ACTIVE"
