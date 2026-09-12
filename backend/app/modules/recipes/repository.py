from datetime import date

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.db.models.catalog import Dish, Ingredient, RecipeItem, RecipeVersion, Unit, UnitConversion


class RecipesRepository:
    def list_recipes(
        self,
        session: Session,
        *,
        limit: int,
        offset: int,
        dish_id: int | None,
        status: str | None,
    ) -> tuple[list[RecipeVersion], int]:
        conditions = []
        if dish_id is not None:
            conditions.append(RecipeVersion.dish_id == dish_id)
        if status is not None:
            conditions.append(RecipeVersion.status == status)
        statement = (
            select(RecipeVersion)
            .options(joinedload(RecipeVersion.dish))
            .where(*conditions)
            .order_by(RecipeVersion.recipe_version_id)
            .limit(limit)
            .offset(offset)
        )
        total = session.scalar(select(func.count()).select_from(RecipeVersion).where(*conditions))
        return list(session.scalars(statement)), int(total or 0)

    def get_recipe(
        self, session: Session, recipe_version_id: int, *, for_update: bool = False
    ) -> RecipeVersion | None:
        statement = (
            select(RecipeVersion)
            .options(joinedload(RecipeVersion.dish))
            .where(RecipeVersion.recipe_version_id == recipe_version_id)
        )
        if for_update:
            # Restrict the lock to the recipe, not the nullable side of the eager join.
            statement = statement.with_for_update(of=RecipeVersion).execution_options(
                populate_existing=True
            )
        return session.scalar(statement)

    def get_recipe_dish_id(self, session: Session, recipe_version_id: int) -> int | None:
        return session.scalar(
            select(RecipeVersion.dish_id).where(
                RecipeVersion.recipe_version_id == recipe_version_id
            )
        )

    def get_dish(self, session: Session, dish_id: int, *, for_update: bool = False) -> Dish | None:
        statement = select(Dish).where(Dish.dish_id == dish_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return session.scalar(statement)

    def next_version_no(self, session: Session, dish_id: int) -> int:
        latest = session.scalar(
            select(func.max(RecipeVersion.version_no)).where(RecipeVersion.dish_id == dish_id)
        )
        return int(latest or 0) + 1

    def lock_dish_versions(self, session: Session, dish_id: int) -> list[RecipeVersion]:
        return list(
            session.scalars(
                select(RecipeVersion)
                .where(RecipeVersion.dish_id == dish_id)
                .order_by(RecipeVersion.recipe_version_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )

    def get_active_recipe(
        self, session: Session, dish_id: int, today: date
    ) -> RecipeVersion | None:
        return session.scalar(
            select(RecipeVersion)
            .options(joinedload(RecipeVersion.dish))
            .where(
                RecipeVersion.dish_id == dish_id,
                RecipeVersion.status == "ACTIVE",
                or_(RecipeVersion.effective_from.is_(None), RecipeVersion.effective_from <= today),
                or_(RecipeVersion.effective_to.is_(None), RecipeVersion.effective_to >= today),
            )
        )

    def list_items(self, session: Session, recipe_version_id: int) -> list[RecipeItem]:
        # RecipeVersion has no items relationship in the existing mapping.
        # This single eager query loads all items and their display information.
        return list(
            session.scalars(
                select(RecipeItem)
                .options(
                    joinedload(RecipeItem.ingredient).joinedload(Ingredient.base_unit),
                    joinedload(RecipeItem.unit),
                )
                .where(RecipeItem.recipe_version_id == recipe_version_id)
                .order_by(RecipeItem.recipe_item_id)
            )
        )

    def get_ingredients(self, session: Session, ingredient_ids: set[int]) -> dict[int, Ingredient]:
        return {
            row.ingredient_id: row
            for row in session.scalars(
                select(Ingredient)
                .options(joinedload(Ingredient.base_unit))
                .where(Ingredient.ingredient_id.in_(ingredient_ids))
            )
        }

    def get_units(self, session: Session, unit_ids: set[int]) -> dict[int, Unit]:
        return {
            row.unit_id: row
            for row in session.scalars(select(Unit).where(Unit.unit_id.in_(unit_ids)))
        }

    def get_conversions(
        self, session: Session, unit_ids: set[int], base_unit_ids: set[int]
    ) -> dict[tuple[int, int], UnitConversion]:
        return {
            (row.from_unit_id, row.to_unit_id): row
            for row in session.scalars(
                select(UnitConversion).where(
                    UnitConversion.from_unit_id.in_(unit_ids),
                    UnitConversion.to_unit_id.in_(base_unit_ids),
                )
            )
        }

    def delete_items(self, session: Session, recipe_version_id: int) -> None:
        # Execute DELETE before inserting replacements with the same ingredient IDs.
        session.execute(delete(RecipeItem).where(RecipeItem.recipe_version_id == recipe_version_id))

    def add(self, session: Session, entity: RecipeVersion | RecipeItem) -> None:
        session.add(entity)
