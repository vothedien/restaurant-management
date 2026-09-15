"""Inventory consumption boundary for the future kitchen completion service.

Sales currently has no order-item status transition endpoint. A future caller
must pin the recipe on the order item, set COMPLETED and completed_at, invoke
consume_in_transaction in the same Session, and commit only after it succeeds.
The standalone wrapper processes persisted completed items without creating or
changing a sales workflow. It deliberately exposes no public completion route.
"""

from decimal import Decimal, localcontext

from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.db.models.inventory import StockMovement
from app.modules.inventory.consumption_repository import ConsumptionRepository
from app.modules.inventory.consumption_schemas import (
    ConsumptionMovementRead,
    ConsumptionResult,
    IngredientRequirement,
)
from app.modules.inventory.stock_common import require_actor, transaction
from app.modules.inventory.stock_service import StockService


class ConsumptionService:
    def __init__(
        self,
        repository: ConsumptionRepository | None = None,
        stock_service: StockService | None = None,
    ) -> None:
        self.repository = repository or ConsumptionRepository()
        self.stock_service = stock_service or StockService()

    def consume_completed_item(
        self, session: Session, order_item_id: int, *, performed_by: int | None = None
    ) -> ConsumptionResult:
        """Commit one already completed order item's consumption, or roll it all back."""
        with transaction(session):
            result = self.consume_in_transaction(session, order_item_id, performed_by=performed_by)
        return result

    def consume_in_transaction(
        self, session: Session, order_item_id: int, *, performed_by: int | None = None
    ) -> ConsumptionResult:
        """Flush without committing; the caller owns commit/rollback of completion.

        Missing recipe pins are business errors (HTTP 400 if mapped by the app).
        Never substitute today's recipe for the version used to prepare a dish.
        Published recipe quantities already contain the base-unit conversion;
        changing a unit conversion later must not change historical consumption.
        """
        # Persist the caller's completion first. The subsequent locking read must
        # not overwrite pending COMPLETED/completed_at with older identity state.
        session.flush()
        order_item = self.repository.lock_order_item(session, order_item_id)
        if order_item is None:
            raise NotFoundError("Order item not found")
        if order_item.status != "COMPLETED" or order_item.completed_at is None:
            raise ConflictError("Only completed order items with completed_at can consume stock")
        if order_item.recipe_version_id is None:
            raise BusinessRuleError("A pinned recipe version is required for stock consumption")
        if performed_by is not None:
            require_actor(session, performed_by)

        recipe = self.repository.get_recipe(session, order_item.recipe_version_id)
        if recipe is None:
            raise NotFoundError("Pinned recipe version not found")
        if recipe.dish_id != order_item.dish_id:
            raise BusinessRuleError("Pinned recipe version does not belong to the order dish")
        if recipe.status not in {"ACTIVE", "INACTIVE", "EXPIRED"}:
            raise BusinessRuleError("Stock consumption requires a published recipe version")

        existing = self.repository.list_consumption(session, order_item_id)
        if existing:
            # The source lock serializes all consumers. No inventory write is
            # attempted on retries, including when stock is now insufficient.
            requirements: dict[int, Decimal] = {}
            for movement in existing:
                if movement.direction != "OUT":
                    raise ConflictError("Existing order consumption has an invalid direction")
                requirements[movement.ingredient_id] = (
                    requirements.get(movement.ingredient_id, Decimal("0")) + movement.quantity
                )
            return self._result(
                order_item_id, recipe.recipe_version_id, True, requirements, existing
            )

        recipe_items = self.repository.list_recipe_items(session, recipe.recipe_version_id)
        if not recipe_items:
            raise BusinessRuleError("Cannot consume stock for an empty recipe")
        requirements = {}
        with localcontext() as context:
            context.prec = 40
            for item in recipe_items:
                quantity = item.base_quantity * Decimal(order_item.quantity)
                if quantity <= 0 or quantity > Decimal("99999999999.999"):
                    raise BusinessRuleError("Recipe consumption is outside the supported range")
                requirements[item.ingredient_id] = quantity

        movements = self.stock_service.consume(
            session,
            requirements,
            performed_by=performed_by,
            order_item_id=order_item_id,
            reason=f"Completed order item {order_item_id}; recipe {recipe.recipe_version_id}",
        )
        session.flush()
        return self._result(order_item_id, recipe.recipe_version_id, False, requirements, movements)

    @staticmethod
    def _result(
        order_item_id: int,
        recipe_version_id: int,
        already_consumed: bool,
        requirements: dict[int, Decimal],
        movements: list[StockMovement],
    ) -> ConsumptionResult:
        # Materialize while still inside the transaction, before commit expires
        # ORM attributes and could issue a second query during response rendering.
        return ConsumptionResult(
            order_item_id=order_item_id,
            recipe_version_id=recipe_version_id,
            already_consumed=already_consumed,
            requirements=[
                IngredientRequirement(ingredient_id=ingredient_id, base_quantity=quantity)
                for ingredient_id, quantity in sorted(requirements.items())
            ],
            movements=[ConsumptionMovementRead.model_validate(row) for row in movements],
        )
