from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.db.models.catalog import Ingredient, RecipeItem, Unit, UnitConversion
from app.db.models.inventory import StockLot, StockMovement, SupplierIngredient


class InventoryRepository:
    @staticmethod
    def lock_ingredient(session: Session, ingredient_id: int) -> Ingredient | None:
        return session.scalar(
            select(Ingredient)
            .where(Ingredient.ingredient_id == ingredient_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    @staticmethod
    def has_quantity_references(session: Session, ingredient_id: int) -> bool:
        return bool(
            session.scalar(
                select(
                    or_(
                        *[
                            exists().where(model.ingredient_id == ingredient_id)
                            for model in (RecipeItem, SupplierIngredient, StockLot, StockMovement)
                        ]
                    )
                )
            )
        )

    def list_units(
        self, session: Session, *, limit: int, offset: int, search: str | None
    ) -> tuple[list[Unit], int]:
        conditions = []
        if search:
            pattern = f"%{search}%"
            conditions.append(or_(Unit.unit_code.ilike(pattern), Unit.unit_name.ilike(pattern)))
        statement = (
            select(Unit).where(*conditions).order_by(Unit.unit_id).limit(limit).offset(offset)
        )
        total_statement = select(func.count()).select_from(Unit).where(*conditions)
        return list(session.scalars(statement)), int(session.scalar(total_statement) or 0)

    def get_unit(self, session: Session, unit_id: int) -> Unit | None:
        return session.get(Unit, unit_id)

    def get_unit_by_code(self, session: Session, unit_code: str) -> Unit | None:
        return session.scalar(select(Unit).where(Unit.unit_code == unit_code))

    def list_conversions(
        self, session: Session, *, limit: int, offset: int
    ) -> tuple[list[UnitConversion], int]:
        statement = (
            select(UnitConversion)
            .options(
                joinedload(UnitConversion.from_unit),
                joinedload(UnitConversion.to_unit),
            )
            .order_by(UnitConversion.conversion_id)
            .limit(limit)
            .offset(offset)
        )
        total_statement = select(func.count()).select_from(UnitConversion)
        return list(session.scalars(statement)), int(session.scalar(total_statement) or 0)

    def get_conversion(self, session: Session, conversion_id: int) -> UnitConversion | None:
        statement = (
            select(UnitConversion)
            .options(
                joinedload(UnitConversion.from_unit),
                joinedload(UnitConversion.to_unit),
            )
            .where(UnitConversion.conversion_id == conversion_id)
        )
        return session.scalar(statement)

    def get_conversion_by_pair(
        self,
        session: Session,
        *,
        from_unit_id: int,
        to_unit_id: int,
        exclude_conversion_id: int | None = None,
    ) -> UnitConversion | None:
        statement = select(UnitConversion).where(
            UnitConversion.from_unit_id == from_unit_id,
            UnitConversion.to_unit_id == to_unit_id,
        )
        if exclude_conversion_id is not None:
            statement = statement.where(UnitConversion.conversion_id != exclude_conversion_id)
        return session.scalar(statement)

    def list_ingredients(
        self,
        session: Session,
        *,
        limit: int,
        offset: int,
        search: str | None,
        status: str | None,
    ) -> tuple[list[Ingredient], int]:
        conditions = []
        if search:
            pattern = f"%{search}%"
            conditions.append(
                or_(
                    Ingredient.ingredient_code.ilike(pattern),
                    Ingredient.ingredient_name.ilike(pattern),
                )
            )
        if status:
            conditions.append(Ingredient.status == status)
        statement = (
            select(Ingredient)
            .options(joinedload(Ingredient.base_unit))
            .where(*conditions)
            .order_by(Ingredient.ingredient_id)
            .limit(limit)
            .offset(offset)
        )
        total_statement = select(func.count()).select_from(Ingredient).where(*conditions)
        return list(session.scalars(statement)), int(session.scalar(total_statement) or 0)

    def get_ingredient(self, session: Session, ingredient_id: int) -> Ingredient | None:
        statement = (
            select(Ingredient)
            .options(joinedload(Ingredient.base_unit))
            .where(Ingredient.ingredient_id == ingredient_id)
        )
        return session.scalar(statement)

    def get_ingredient_by_code(self, session: Session, ingredient_code: str) -> Ingredient | None:
        return session.scalar(
            select(Ingredient).where(Ingredient.ingredient_code == ingredient_code)
        )

    def add(self, session: Session, entity: Unit | UnitConversion | Ingredient) -> None:
        session.add(entity)
