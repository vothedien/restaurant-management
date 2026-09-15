from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.catalog import RecipeItem, RecipeVersion
from app.db.models.inventory import StockMovement
from app.db.models.sales import OrderItem


class ConsumptionRepository:
    def lock_order_item(self, session: Session, order_item_id: int) -> OrderItem | None:
        # Every retry locks the same persisted source before testing for movements.
        # Refresh ORM state after waiting for a concurrent transaction to finish.
        return session.scalar(
            select(OrderItem)
            .where(OrderItem.order_item_id == order_item_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def get_recipe(self, session: Session, recipe_version_id: int) -> RecipeVersion | None:
        return session.scalar(
            select(RecipeVersion)
            .where(RecipeVersion.recipe_version_id == recipe_version_id)
            .execution_options(populate_existing=True)
        )

    def list_recipe_items(self, session: Session, recipe_version_id: int) -> list[RecipeItem]:
        return list(
            session.scalars(
                select(RecipeItem)
                .where(RecipeItem.recipe_version_id == recipe_version_id)
                .order_by(RecipeItem.ingredient_id)
                .execution_options(populate_existing=True)
            )
        )

    def list_consumption(self, session: Session, order_item_id: int) -> list[StockMovement]:
        return list(
            session.scalars(
                select(StockMovement)
                .where(
                    StockMovement.order_item_id == order_item_id,
                    StockMovement.movement_type == "CONSUMPTION",
                )
                .order_by(StockMovement.stock_movement_id)
                .execution_options(populate_existing=True)
            )
        )
