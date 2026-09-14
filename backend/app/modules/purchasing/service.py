from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError, BusinessRuleError, ConflictError, NotFoundError
from app.db.models.catalog import Ingredient, Unit
from app.db.models.inventory import Supplier, SupplierIngredient
from app.modules.purchasing.repository import PurchasingRepository, SupplierIngredientRow
from app.modules.purchasing.schemas import (
    SupplierCreate,
    SupplierIngredientCreate,
    SupplierIngredientRead,
    SupplierIngredientUpdate,
    SupplierRead,
    SupplierUpdate,
)


class PurchasingStorageError(ApplicationError):
    """A storage failure whose driver details must not reach the API client."""

    status_code = 503


class PurchasingService:
    def __init__(self, repository: PurchasingRepository | None = None) -> None:
        self.repository = repository or PurchasingRepository()

    def list_suppliers(
        self,
        session: Session,
        *,
        limit: int,
        offset: int,
        search: str | None,
        status: str | None,
    ) -> tuple[list[SupplierRead], int]:
        with self._database_errors(session):
            suppliers, total = self.repository.list_suppliers(
                session, limit=limit, offset=offset, search=search, status=status
            )
            return [SupplierRead.model_validate(supplier) for supplier in suppliers], total

    def get_supplier(self, session: Session, supplier_id: int) -> SupplierRead:
        with self._database_errors(session):
            return SupplierRead.model_validate(self._require_supplier(session, supplier_id))

    def create_supplier(self, session: Session, data: SupplierCreate) -> SupplierRead:
        with self._transaction(session):
            if self.repository.get_supplier_by_code(session, data.supplier_code) is not None:
                raise ConflictError("Supplier code already exists")
            supplier = Supplier(**data.model_dump())
            self.repository.add(session, supplier)
            session.flush()
            result = SupplierRead.model_validate(supplier)
        return result

    def update_supplier(
        self, session: Session, supplier_id: int, data: SupplierUpdate
    ) -> SupplierRead:
        with self._transaction(session):
            supplier = self._require_supplier(session, supplier_id, for_update=True)
            changes = data.model_dump(exclude_unset=True)
            if "supplier_code" in changes:
                existing = self.repository.get_supplier_by_code(session, changes["supplier_code"])
                if existing is not None and existing.supplier_id != supplier_id:
                    raise ConflictError("Supplier code already exists")
            if changes.get("status") == "INACTIVE":
                self._deactivate_supplier_mappings(session, supplier_id)
            for field, value in changes.items():
                setattr(supplier, field, value)
            supplier.updated_at = datetime.now(UTC)
            session.flush()
            result = SupplierRead.model_validate(supplier)
        return result

    def deactivate_supplier(self, session: Session, supplier_id: int) -> SupplierRead:
        with self._transaction(session):
            supplier = self._require_supplier(session, supplier_id, for_update=True)
            self._deactivate_supplier_mappings(session, supplier_id)
            supplier.status = "INACTIVE"
            supplier.updated_at = datetime.now(UTC)
            session.flush()
            result = SupplierRead.model_validate(supplier)
        return result

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
    ) -> tuple[list[SupplierIngredientRead], int]:
        with self._database_errors(session):
            rows, total = self.repository.list_supplier_ingredients(
                session,
                limit=limit,
                offset=offset,
                supplier_id=supplier_id,
                ingredient_id=ingredient_id,
                is_active=is_active,
                is_preferred=is_preferred,
            )
            return [self._mapping_read(row) for row in rows], total

    def get_supplier_ingredient(
        self, session: Session, supplier_ingredient_id: int
    ) -> SupplierIngredientRead:
        with self._database_errors(session):
            return self._mapping_detail(session, supplier_ingredient_id)

    def create_supplier_ingredient(
        self, session: Session, data: SupplierIngredientCreate
    ) -> SupplierIngredientRead:
        with self._transaction(session):
            supplier = self._require_supplier(session, data.supplier_id, for_update=True)
            ingredient = self._require_ingredient(session, data.ingredient_id, for_update=True)
            self._require_active_references(supplier, ingredient)
            self._require_active_unit(session, data.purchase_unit_id)
            if self.repository.get_mapping_by_pair(session, data.supplier_id, data.ingredient_id):
                raise ConflictError("Supplier ingredient mapping already exists")
            mappings = self.repository.lock_ingredient_mappings(session, data.ingredient_id)
            preferred = data.is_preferred and data.is_active
            if preferred:
                self._clear_preferred(session, mappings)
            # Add only after old preferred rows have been flushed. This remains
            # safe even if a caller uses a session with autoflush enabled.
            values = data.model_dump()
            values["is_preferred"] = preferred
            mapping = SupplierIngredient(**values)
            self.repository.add(session, mapping)
            session.flush()
            result = self._mapping_detail(session, mapping.supplier_ingredient_id)
        return result

    def update_supplier_ingredient(
        self,
        session: Session,
        supplier_ingredient_id: int,
        data: SupplierIngredientUpdate,
    ) -> SupplierIngredientRead:
        with self._transaction(session):
            supplier, ingredient, mappings, mapping = self._lock_mapping(
                session, supplier_ingredient_id
            )
            changes = data.model_dump(exclude_unset=True)
            active = changes.get("is_active", mapping.is_active)
            preferred = changes.get("is_preferred", mapping.is_preferred) and active
            if active:
                self._require_active_references(supplier, ingredient)
            if active or "purchase_unit_id" in changes:
                self._require_active_unit(
                    session, changes.get("purchase_unit_id", mapping.purchase_unit_id)
                )
            if preferred:
                self._clear_preferred(session, mappings)
            for field, value in changes.items():
                if field not in {"is_preferred", "is_active"}:
                    setattr(mapping, field, value)
            mapping.is_active = active
            mapping.is_preferred = preferred
            session.flush()
            result = self._mapping_detail(session, supplier_ingredient_id)
        return result

    def deactivate_supplier_ingredient(
        self, session: Session, supplier_ingredient_id: int
    ) -> SupplierIngredientRead:
        with self._transaction(session):
            _, _, _, mapping = self._lock_mapping(session, supplier_ingredient_id)
            mapping.is_active = False
            mapping.is_preferred = False
            session.flush()
            result = self._mapping_detail(session, supplier_ingredient_id)
        return result

    def _lock_mapping(
        self, session: Session, supplier_ingredient_id: int
    ) -> tuple[Supplier, Ingredient, list[SupplierIngredient], SupplierIngredient]:
        # Read immutable FKs only, without locking the target first. All writes
        # lock supplier -> ingredient -> mappings ordered by ID. Locking the
        # ingredient also serializes creation when there are no mappings yet.
        references = self.repository.get_mapping_reference_ids(session, supplier_ingredient_id)
        if references is None:
            raise NotFoundError("Supplier ingredient mapping not found")
        supplier_id, ingredient_id = references
        supplier = self._require_supplier(session, supplier_id, for_update=True)
        ingredient = self._require_ingredient(session, ingredient_id, for_update=True)
        mappings = self.repository.lock_ingredient_mappings(session, ingredient_id)
        mapping = next(
            (row for row in mappings if row.supplier_ingredient_id == supplier_ingredient_id), None
        )
        if mapping is None:
            raise NotFoundError("Supplier ingredient mapping not found")
        return supplier, ingredient, mappings, mapping

    def _require_supplier(
        self, session: Session, supplier_id: int, *, for_update: bool = False
    ) -> Supplier:
        supplier = self.repository.get_supplier(session, supplier_id, for_update=for_update)
        if supplier is None:
            raise NotFoundError("Supplier not found")
        return supplier

    def _require_ingredient(
        self, session: Session, ingredient_id: int, *, for_update: bool = False
    ) -> Ingredient:
        ingredient = self.repository.get_ingredient(session, ingredient_id, for_update=for_update)
        if ingredient is None:
            raise NotFoundError("Ingredient not found")
        return ingredient

    @staticmethod
    def _require_active_references(supplier: Supplier, ingredient: Ingredient) -> None:
        if supplier.status != "ACTIVE":
            raise BusinessRuleError("Supplier must be active")
        if ingredient.status != "ACTIVE":
            raise BusinessRuleError("Ingredient must be active")

    def _require_active_unit(self, session: Session, unit_id: int) -> Unit:
        unit = self.repository.get_unit(session, unit_id)
        if unit is None:
            raise NotFoundError("Purchase unit not found")
        if not unit.is_active:
            raise BusinessRuleError("Purchase unit must be active")
        return unit

    def _deactivate_supplier_mappings(self, session: Session, supplier_id: int) -> None:
        # Supplier lock prevents concurrent creation/reactivation. Both deletion
        # and preferred changes lock mapping rows in the same primary-key order.
        for mapping in self.repository.lock_supplier_mappings(session, supplier_id):
            mapping.is_active = False
            mapping.is_preferred = False

    @staticmethod
    def _clear_preferred(session: Session, mappings: list[SupplierIngredient]) -> None:
        for mapping in mappings:
            if mapping.is_preferred:
                mapping.is_preferred = False
        # PostgreSQL's partial unique index is immediate, not deferred. Persist
        # old flags before setting the new preferred flag, regardless of PK order.
        session.flush()

    def _mapping_detail(
        self, session: Session, supplier_ingredient_id: int
    ) -> SupplierIngredientRead:
        row = self.repository.get_supplier_ingredient(session, supplier_ingredient_id)
        if row is None:
            raise NotFoundError("Supplier ingredient mapping not found")
        return self._mapping_read(row)

    @staticmethod
    def _mapping_read(row: SupplierIngredientRow) -> SupplierIngredientRead:
        mapping, supplier, ingredient, unit = row
        return SupplierIngredientRead(
            supplier_ingredient_id=mapping.supplier_ingredient_id,
            supplier_id=mapping.supplier_id,
            ingredient_id=mapping.ingredient_id,
            supplier_sku=mapping.supplier_sku,
            purchase_unit_id=mapping.purchase_unit_id,
            base_qty_per_purchase_unit=mapping.base_qty_per_purchase_unit,
            lead_time_days=mapping.lead_time_days,
            minimum_order_qty=mapping.minimum_order_qty,
            latest_unit_price=mapping.latest_unit_price,
            is_preferred=mapping.is_preferred,
            is_active=mapping.is_active,
            supplier=supplier,
            ingredient=ingredient,
            purchase_unit=unit,
        )

    @classmethod
    @contextmanager
    def _transaction(cls, session: Session) -> Iterator[None]:
        # Queries start the transaction through SQLAlchemy autobegin. Materialize
        # responses before commit so expired attributes cannot trigger lazy reads.
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
                "Purchasing data conflicts with an existing record or concurrent change"
            ) from error
        except SQLAlchemyError as error:
            session.rollback()
            raise PurchasingStorageError("Purchasing storage is temporarily unavailable") from error
        except Exception:
            session.rollback()
            raise
