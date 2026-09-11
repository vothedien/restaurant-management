from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.db.models.catalog import Ingredient, Unit, UnitConversion
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schemas import (
    IngredientCreate,
    IngredientUpdate,
    UnitConversionCreate,
    UnitConversionUpdate,
    UnitCreate,
    UnitUpdate,
)


class InventoryService:
    def __init__(self, repository: InventoryRepository | None = None) -> None:
        self.repository = repository or InventoryRepository()

    def list_units(
        self, session: Session, *, limit: int, offset: int, search: str | None
    ) -> tuple[list[Unit], int]:
        return self.repository.list_units(session, limit=limit, offset=offset, search=search)

    def get_unit(self, session: Session, unit_id: int) -> Unit:
        unit = self.repository.get_unit(session, unit_id)
        if unit is None:
            raise NotFoundError("Unit not found")
        return unit

    def create_unit(self, session: Session, data: UnitCreate) -> Unit:
        if self.repository.get_unit_by_code(session, data.unit_code):
            raise ConflictError("Unit code already exists")
        unit = Unit(
            unit_code=data.unit_code,
            unit_name=data.unit_name,
            dimension=data.dimension,
            is_active=data.is_active,
        )
        self.repository.add(session, unit)
        return self._save(session, unit, "Unit code already exists")

    def update_unit(self, session: Session, unit_id: int, data: UnitUpdate) -> Unit:
        unit = self.get_unit(session, unit_id)
        changes = data.model_dump(exclude_unset=True)
        unit_code = changes.get("unit_code")
        if unit_code and unit_code != unit.unit_code:
            existing = self.repository.get_unit_by_code(session, unit_code)
            if existing and existing.unit_id != unit_id:
                raise ConflictError("Unit code already exists")
        for field, value in changes.items():
            setattr(unit, field, value)
        return self._save(session, unit, "Unit code already exists")

    def deactivate_unit(self, session: Session, unit_id: int) -> Unit:
        unit = self.get_unit(session, unit_id)
        unit.is_active = False
        return self._save(session, unit, "Unable to deactivate unit")

    def list_conversions(
        self, session: Session, *, limit: int, offset: int
    ) -> tuple[list[UnitConversion], int]:
        return self.repository.list_conversions(session, limit=limit, offset=offset)

    def get_conversion(self, session: Session, conversion_id: int) -> UnitConversion:
        conversion = self.repository.get_conversion(session, conversion_id)
        if conversion is None:
            raise NotFoundError("Unit conversion not found")
        return conversion

    def create_conversion(self, session: Session, data: UnitConversionCreate) -> UnitConversion:
        self._validate_conversion(
            session,
            from_unit_id=data.from_unit_id,
            to_unit_id=data.to_unit_id,
        )
        if self.repository.get_conversion_by_pair(
            session, from_unit_id=data.from_unit_id, to_unit_id=data.to_unit_id
        ):
            raise ConflictError("Unit conversion already exists")
        conversion = UnitConversion(
            from_unit_id=data.from_unit_id,
            to_unit_id=data.to_unit_id,
            factor=data.factor,
        )
        self.repository.add(session, conversion)
        self._save(session, conversion, "Unit conversion already exists")
        return self.get_conversion(session, conversion.conversion_id)

    def update_conversion(
        self, session: Session, conversion_id: int, data: UnitConversionUpdate
    ) -> UnitConversion:
        conversion = self.get_conversion(session, conversion_id)
        changes = data.model_dump(exclude_unset=True)
        from_unit_id = changes.get("from_unit_id", conversion.from_unit_id)
        to_unit_id = changes.get("to_unit_id", conversion.to_unit_id)
        self._validate_conversion(session, from_unit_id=from_unit_id, to_unit_id=to_unit_id)
        existing = self.repository.get_conversion_by_pair(
            session,
            from_unit_id=from_unit_id,
            to_unit_id=to_unit_id,
            exclude_conversion_id=conversion_id,
        )
        if existing:
            raise ConflictError("Unit conversion already exists")
        for field, value in changes.items():
            setattr(conversion, field, value)
        self._save(session, conversion, "Unit conversion already exists")
        return self.get_conversion(session, conversion_id)

    def delete_conversion(self, session: Session, conversion_id: int) -> None:
        conversion = self.get_conversion(session, conversion_id)
        session.delete(conversion)
        self._save(session, None, "Unable to delete unit conversion")

    def list_ingredients(
        self,
        session: Session,
        *,
        limit: int,
        offset: int,
        search: str | None,
        status: str | None,
    ) -> tuple[list[Ingredient], int]:
        return self.repository.list_ingredients(
            session, limit=limit, offset=offset, search=search, status=status
        )

    def get_ingredient(self, session: Session, ingredient_id: int) -> Ingredient:
        ingredient = self.repository.get_ingredient(session, ingredient_id)
        if ingredient is None:
            raise NotFoundError("Ingredient not found")
        return ingredient

    def create_ingredient(self, session: Session, data: IngredientCreate) -> Ingredient:
        if self.repository.get_ingredient_by_code(session, data.ingredient_code):
            raise ConflictError("Ingredient code already exists")
        self._require_active_unit(session, data.base_unit_id, "Base unit")
        ingredient = Ingredient(
            ingredient_code=data.ingredient_code,
            ingredient_name=data.ingredient_name,
            base_unit_id=data.base_unit_id,
            manages_lot=data.manages_lot,
            default_shelf_life_days=data.default_shelf_life_days,
            minimum_stock_qty=data.minimum_stock_qty,
            safety_stock_qty=data.safety_stock_qty,
            status=data.status,
        )
        self.repository.add(session, ingredient)
        self._save(session, ingredient, "Ingredient code already exists")
        return self.get_ingredient(session, ingredient.ingredient_id)

    def update_ingredient(
        self, session: Session, ingredient_id: int, data: IngredientUpdate
    ) -> Ingredient:
        ingredient = self.get_ingredient(session, ingredient_id)
        changes = data.model_dump(exclude_unset=True)
        ingredient_code = changes.get("ingredient_code")
        if ingredient_code and ingredient_code != ingredient.ingredient_code:
            existing = self.repository.get_ingredient_by_code(session, ingredient_code)
            if existing and existing.ingredient_id != ingredient_id:
                raise ConflictError("Ingredient code already exists")
        base_unit_id = changes.get("base_unit_id", ingredient.base_unit_id)
        self._require_active_unit(session, base_unit_id, "Base unit")
        for field, value in changes.items():
            setattr(ingredient, field, value)
        ingredient.updated_at = datetime.now(UTC)
        self._save(session, ingredient, "Ingredient code already exists")
        return self.get_ingredient(session, ingredient_id)

    def deactivate_ingredient(self, session: Session, ingredient_id: int) -> Ingredient:
        ingredient = self.get_ingredient(session, ingredient_id)
        ingredient.status = "INACTIVE"
        ingredient.updated_at = datetime.now(UTC)
        self._save(session, ingredient, "Unable to deactivate ingredient")
        return self.get_ingredient(session, ingredient_id)

    def _validate_conversion(self, session: Session, *, from_unit_id: int, to_unit_id: int) -> None:
        if from_unit_id == to_unit_id:
            raise BusinessRuleError("Source and destination units must be different")
        from_unit = self._require_active_unit(session, from_unit_id, "Source unit")
        to_unit = self._require_active_unit(session, to_unit_id, "Destination unit")
        if from_unit.dimension != to_unit.dimension:
            raise BusinessRuleError("Unit conversions require matching dimensions")

    def _require_active_unit(self, session: Session, unit_id: int, label: str) -> Unit:
        unit = self.repository.get_unit(session, unit_id)
        if unit is None:
            raise NotFoundError(f"{label} not found")
        if not unit.is_active:
            raise BusinessRuleError(f"{label} must be active")
        return unit

    @staticmethod
    def _save(
        session: Session,
        entity: Unit | UnitConversion | Ingredient | None,
        conflict_message: str,
    ) -> Unit | UnitConversion | Ingredient | None:
        try:
            session.commit()
        except IntegrityError as error:
            session.rollback()
            raise ConflictError(conflict_message) from error
        if entity is not None:
            session.refresh(entity)
        return entity
