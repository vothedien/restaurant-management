from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.db.models.catalog import Ingredient, Unit
from app.db.models.inventory import Supplier, SupplierIngredient

SupplierIngredientRow = tuple[SupplierIngredient, Supplier, Ingredient, Unit]


class PurchasingRepository:
    def list_suppliers(
        self,
        session: Session,
        *,
        limit: int,
        offset: int,
        search: str | None,
        status: str | None,
    ) -> tuple[list[Supplier], int]:
        conditions = []
        if search:
            # Treat search text literally, including SQL LIKE wildcard characters.
            escaped = search.replace("/", "//").replace("%", "/%").replace("_", "/_")
            pattern = f"%{escaped}%"
            conditions.append(
                or_(
                    *(
                        column.ilike(pattern, escape="/")
                        for column in (
                            Supplier.supplier_code,
                            Supplier.supplier_name,
                            Supplier.contact_name,
                            Supplier.phone,
                            Supplier.email,
                        )
                    )
                )
            )
        if status is not None:
            conditions.append(Supplier.status == status)
        statement = (
            select(Supplier)
            .where(*conditions)
            .order_by(Supplier.supplier_id)
            .limit(limit)
            .offset(offset)
        )
        total = session.scalar(select(func.count()).select_from(Supplier).where(*conditions))
        return list(session.scalars(statement)), int(total or 0)

    def get_supplier(
        self, session: Session, supplier_id: int, *, for_update: bool = False
    ) -> Supplier | None:
        statement = select(Supplier).where(Supplier.supplier_id == supplier_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return session.scalar(statement)

    def get_supplier_by_code(self, session: Session, supplier_code: str) -> Supplier | None:
        return session.scalar(select(Supplier).where(Supplier.supplier_code == supplier_code))

    @staticmethod
    def _mapping_details() -> Select:
        # Only supplier has an ORM relationship in the existing model. Explicit
        # joins eagerly load all summaries without altering production mappings.
        return (
            select(SupplierIngredient, Supplier, Ingredient, Unit)
            .join(Supplier, Supplier.supplier_id == SupplierIngredient.supplier_id)
            .join(Ingredient, Ingredient.ingredient_id == SupplierIngredient.ingredient_id)
            .join(Unit, Unit.unit_id == SupplierIngredient.purchase_unit_id)
        )

    def list_supplier_ingredients(
        self,
        session: Session,
        *,
        limit: int,
        offset: int,
        supplier_id: int | None,
        ingredient_id: int | None,
        is_active: bool | None,
        is_preferred: bool | None,
    ) -> tuple[list[SupplierIngredientRow], int]:
        conditions = []
        for column, value in (
            (SupplierIngredient.supplier_id, supplier_id),
            (SupplierIngredient.ingredient_id, ingredient_id),
            (SupplierIngredient.is_active, is_active),
            (SupplierIngredient.is_preferred, is_preferred),
        ):
            if value is not None:
                conditions.append(column == value)
        statement = (
            self._mapping_details()
            .where(*conditions)
            .order_by(SupplierIngredient.supplier_ingredient_id)
            .limit(limit)
            .offset(offset)
        )
        total = session.scalar(
            select(func.count()).select_from(SupplierIngredient).where(*conditions)
        )
        return [tuple(row) for row in session.execute(statement)], int(total or 0)

    def get_supplier_ingredient(
        self, session: Session, supplier_ingredient_id: int
    ) -> SupplierIngredientRow | None:
        row = session.execute(
            self._mapping_details().where(
                SupplierIngredient.supplier_ingredient_id == supplier_ingredient_id
            )
        ).one_or_none()
        return tuple(row) if row is not None else None

    def get_mapping_reference_ids(
        self, session: Session, supplier_ingredient_id: int
    ) -> tuple[int, int] | None:
        row = session.execute(
            select(SupplierIngredient.supplier_id, SupplierIngredient.ingredient_id).where(
                SupplierIngredient.supplier_ingredient_id == supplier_ingredient_id
            )
        ).one_or_none()
        return tuple(row) if row is not None else None

    def get_mapping_by_pair(
        self, session: Session, supplier_id: int, ingredient_id: int
    ) -> SupplierIngredient | None:
        return session.scalar(
            select(SupplierIngredient).where(
                SupplierIngredient.supplier_id == supplier_id,
                SupplierIngredient.ingredient_id == ingredient_id,
            )
        )

    def get_ingredient(
        self, session: Session, ingredient_id: int, *, for_update: bool = False
    ) -> Ingredient | None:
        statement = select(Ingredient).where(Ingredient.ingredient_id == ingredient_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return session.scalar(statement)

    def get_unit(self, session: Session, unit_id: int) -> Unit | None:
        return session.scalar(select(Unit).where(Unit.unit_id == unit_id))

    def lock_ingredient_mappings(
        self, session: Session, ingredient_id: int
    ) -> list[SupplierIngredient]:
        return list(
            session.scalars(
                select(SupplierIngredient)
                .where(SupplierIngredient.ingredient_id == ingredient_id)
                .order_by(SupplierIngredient.supplier_ingredient_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )

    def lock_supplier_mappings(
        self, session: Session, supplier_id: int
    ) -> list[SupplierIngredient]:
        return list(
            session.scalars(
                select(SupplierIngredient)
                .where(SupplierIngredient.supplier_id == supplier_id)
                .order_by(SupplierIngredient.supplier_ingredient_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )

    def add(self, session: Session, entity: Supplier | SupplierIngredient) -> None:
        session.add(entity)
