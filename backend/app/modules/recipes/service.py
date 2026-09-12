from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError, BusinessRuleError, ConflictError, NotFoundError
from app.db.models.catalog import Dish, RecipeItem, RecipeVersion
from app.modules.recipes.repository import RecipesRepository
from app.modules.recipes.schemas import (
    RecipeCreate,
    RecipeDetail,
    RecipeItemRead,
    RecipeItemsReplace,
    RecipeRead,
    RecipeUpdate,
)


class RecipeStorageError(ApplicationError):
    """A database failure whose driver details must not be exposed to clients."""

    status_code = 503


class RecipesService:
    def __init__(self, repository: RecipesRepository | None = None) -> None:
        self.repository = repository or RecipesRepository()

    def list_recipes(
        self,
        session: Session,
        *,
        limit: int,
        offset: int,
        dish_id: int | None,
        status: str | None,
    ) -> tuple[list[RecipeVersion], int]:
        with self._database_errors(session):
            return self.repository.list_recipes(
                session, limit=limit, offset=offset, dish_id=dish_id, status=status
            )

    def get_recipe(self, session: Session, recipe_version_id: int) -> RecipeDetail:
        with self._database_errors(session):
            recipe = self._require_recipe(session, recipe_version_id)
            return self._detail(session, recipe)

    def get_active_recipe(self, session: Session, dish_id: int) -> RecipeDetail:
        with self._database_errors(session):
            self._require_dish(session, dish_id)
            recipe = self.repository.get_active_recipe(session, dish_id, date.today())
            if recipe is None:
                raise NotFoundError("No active recipe is currently effective for this dish")
            return self._detail(session, recipe)

    def create_recipe(self, session: Session, data: RecipeCreate) -> RecipeDetail:
        with self._transaction(session):
            # Lock the parent even when it has no versions yet. All creation and
            # activation requests for the same dish acquire this lock first.
            dish = self._require_dish(session, data.dish_id, for_update=True)
            self._require_active_dish(dish)
            version_no = self.repository.next_version_no(session, dish.dish_id)
            if version_no > 2_147_483_647:
                raise ConflictError("Recipe version number limit reached")
            recipe = RecipeVersion(
                **data.model_dump(), version_no=version_no, status="DRAFT", created_by=None
            )
            self.repository.add(session, recipe)
            session.flush()
            result = self._detail(session, recipe)
        return result

    def update_recipe(
        self, session: Session, recipe_version_id: int, data: RecipeUpdate
    ) -> RecipeDetail:
        with self._transaction(session):
            recipe = self._require_recipe(session, recipe_version_id, for_update=True)
            self._require_draft(recipe)
            changes = data.model_dump(exclude_unset=True)
            self._validate_dates(
                changes.get("effective_from", recipe.effective_from),
                changes.get("effective_to", recipe.effective_to),
            )
            for field, value in changes.items():
                setattr(recipe, field, value)
            session.flush()
            result = self._detail(session, recipe)
        return result

    def replace_items(
        self, session: Session, recipe_version_id: int, data: RecipeItemsReplace
    ) -> RecipeDetail:
        with self._transaction(session):
            recipe = self._require_recipe(session, recipe_version_id, for_update=True)
            self._require_draft(recipe)
            items = self._prepare_items(session, recipe_version_id, data)
            # Validate the whole payload before deleting anything. A later DB
            # failure still rolls back both the DELETE and every INSERT.
            self.repository.delete_items(session, recipe_version_id)
            for item in items:
                self.repository.add(session, item)
            session.flush()
            result = self._detail(session, recipe)
        return result

    def activate_recipe(self, session: Session, recipe_version_id: int) -> RecipeDetail:
        with self._transaction(session):
            # Read only the immutable FK before locking. Do not lock the target
            # first: two activations could otherwise deadlock locking each other.
            dish_id = self.repository.get_recipe_dish_id(session, recipe_version_id)
            if dish_id is None:
                raise NotFoundError("Recipe version not found")
            dish = self._require_dish(session, dish_id, for_update=True)
            versions = self.repository.lock_dish_versions(session, dish_id)
            recipe = next(
                (row for row in versions if row.recipe_version_id == recipe_version_id), None
            )
            if recipe is None:
                raise NotFoundError("Recipe version not found")
            self._require_draft(recipe)
            self._require_active_dish(dish)
            if not self.repository.list_items(session, recipe_version_id):
                raise BusinessRuleError("Cannot activate an empty recipe")
            effective_from = recipe.effective_from or date.today()
            self._validate_dates(effective_from, recipe.effective_to)
            for version in versions:
                if version.status == "ACTIVE":
                    version.status = "INACTIVE"
            # The partial unique index is immediate, not deferred. Persist old
            # statuses before SQLAlchemy is allowed to emit the ACTIVE update.
            session.flush()
            recipe.effective_from = effective_from
            recipe.status = "ACTIVE"
            session.flush()
            result = self._detail(session, recipe)
        return result

    def _prepare_items(
        self, session: Session, recipe_version_id: int, data: RecipeItemsReplace
    ) -> list[RecipeItem]:
        ingredients = self.repository.get_ingredients(
            session, {item.ingredient_id for item in data.items}
        )
        unit_ids = {item.unit_id for item in data.items}
        units = self.repository.get_units(session, unit_ids)
        conversions = self.repository.get_conversions(
            session, unit_ids, {ingredient.base_unit_id for ingredient in ingredients.values()}
        )
        items = []
        for item in data.items:
            ingredient = ingredients.get(item.ingredient_id)
            if ingredient is None:
                raise NotFoundError("Ingredient not found")
            if ingredient.status != "ACTIVE":
                raise BusinessRuleError("Recipe ingredients must be active")
            unit = units.get(item.unit_id)
            if unit is None:
                raise NotFoundError("Unit not found")
            if not unit.is_active:
                raise BusinessRuleError("Recipe units must be active")
            base_unit = ingredient.base_unit
            if base_unit is None:
                raise NotFoundError("Ingredient base unit not found")
            if not base_unit.is_active:
                raise BusinessRuleError("Ingredient base units must be active")
            if unit.dimension != base_unit.dimension:
                raise BusinessRuleError("Recipe units require matching dimensions")
            factor = Decimal("1")
            if unit.unit_id != ingredient.base_unit_id:
                conversion = conversions.get((unit.unit_id, ingredient.base_unit_id))
                if conversion is None:
                    raise BusinessRuleError("No direct conversion from recipe unit to base unit")
                factor = conversion.factor
            # Match NUMERIC(14,3) explicitly, using decimal arithmetic throughout.
            # 14-digit quantities times 18-digit factors need up to 32 digits.
            with localcontext() as context:
                context.prec = 40
                base_quantity = (item.quantity * factor).quantize(
                    Decimal("0.001"), rounding=ROUND_HALF_UP
                )
            if base_quantity <= 0 or base_quantity > Decimal("99999999999.999"):
                raise BusinessRuleError("Converted quantity is outside the supported range")
            items.append(
                RecipeItem(
                    recipe_version_id=recipe_version_id,
                    ingredient_id=item.ingredient_id,
                    unit_id=item.unit_id,
                    quantity=item.quantity,
                    base_quantity=base_quantity,
                )
            )
        return items

    def _require_recipe(
        self, session: Session, recipe_version_id: int, *, for_update: bool = False
    ) -> RecipeVersion:
        recipe = self.repository.get_recipe(session, recipe_version_id, for_update=for_update)
        if recipe is None:
            raise NotFoundError("Recipe version not found")
        return recipe

    def _require_dish(self, session: Session, dish_id: int, *, for_update: bool = False) -> Dish:
        dish = self.repository.get_dish(session, dish_id, for_update=for_update)
        if dish is None:
            raise NotFoundError("Dish not found")
        return dish

    @staticmethod
    def _require_draft(recipe: RecipeVersion) -> None:
        if recipe.status != "DRAFT":
            raise ConflictError("Only DRAFT recipes can be changed or activated")

    @staticmethod
    def _require_active_dish(dish: Dish) -> None:
        if dish.status != "ACTIVE":
            raise BusinessRuleError("Dish must be active")

    @staticmethod
    def _validate_dates(effective_from: date | None, effective_to: date | None) -> None:
        if (
            effective_from is not None
            and effective_to is not None
            and effective_to < effective_from
        ):
            raise BusinessRuleError("effective_to must be on or after effective_from")

    def _detail(self, session: Session, recipe: RecipeVersion) -> RecipeDetail:
        # Materialize before commit to avoid expired ORM attributes causing
        # post-commit lazy loads or failures while rendering a successful write.
        return RecipeDetail(
            **RecipeRead.model_validate(recipe).model_dump(),
            items=[
                RecipeItemRead.model_validate(item)
                for item in self.repository.list_items(session, recipe.recipe_version_id)
            ],
        )

    @classmethod
    @contextmanager
    def _transaction(cls, session: Session) -> Iterator[None]:
        # The first query starts SQLAlchemy's transaction (autobegin). Services
        # alone commit it; repositories never commit or open nested transactions.
        with cls._database_errors(session):
            yield
            session.commit()

    @staticmethod
    @contextmanager
    def _database_errors(session: Session) -> Iterator[None]:
        try:
            yield
        except IntegrityError as error:
            session.rollback()
            raise ConflictError(
                "Recipe data conflicts with an existing record or concurrent change"
            ) from error
        except SQLAlchemyError as error:
            session.rollback()
            raise RecipeStorageError("Recipe storage is temporarily unavailable") from error
        except Exception:
            session.rollback()
            raise
