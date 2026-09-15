from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.db.models.inventory import PurchaseOrder, PurchaseOrderItem, SupplierIngredient
from app.modules.inventory.stock_common import (
    database_errors,
    exact_quantity,
    lock_ingredients,
    money,
    require_actor,
    transaction,
)
from app.modules.purchasing.order_repository import PurchaseOrderRepository
from app.modules.purchasing.order_schemas import (
    PurchaseOrderCreate,
    PurchaseOrderItemInput,
    PurchaseOrderItemRead,
    PurchaseOrderRead,
    PurchaseOrderTransition,
    PurchaseOrderUpdate,
)


class PurchaseOrderService:
    def __init__(self, repository: PurchaseOrderRepository | None = None) -> None:
        self.repository = repository or PurchaseOrderRepository()

    def require_order(self, session: Session, order_id: int, *, lock=False) -> PurchaseOrder:
        order = self.repository.get(session, order_id, lock=lock)
        if order is None:
            raise NotFoundError("Purchase order not found")
        return order

    def read(self, session: Session, order: PurchaseOrder) -> PurchaseOrderRead:
        received = self.repository.received_quantities(session, order.purchase_order_id)
        items = []
        for item in self.repository.items(session, order.purchase_order_id):
            line = PurchaseOrderItemRead.model_validate(item)
            line.received_quantity = received.get(item.purchase_order_item_id, Decimal("0"))
            line.remaining_quantity = item.ordered_quantity - line.received_quantity
            items.append(line)
        values = {
            name: getattr(order, name) for name in PurchaseOrderRead.model_fields if name != "items"
        }
        return PurchaseOrderRead(**values, items=items)

    def get(self, session: Session, order_id: int) -> PurchaseOrderRead:
        with database_errors(session):
            return self.read(session, self.require_order(session, order_id))

    def list(self, session: Session, **filters) -> tuple[list[PurchaseOrderRead], int]:
        with database_errors(session):
            orders, total = self.repository.list(session, **filters)
            return [self.read(session, order) for order in orders], total

    def active_mappings(
        self,
        session: Session,
        supplier_id: int,
        mapping_ids: list[int],
    ) -> dict[int, SupplierIngredient]:
        # Same supplier -> sorted ingredients -> sorted mapping order used by
        # supplier maintenance. The purchase order, if existing, is locked first.
        supplier = self.repository.supplier(session, supplier_id)
        if supplier is None:
            raise NotFoundError("Supplier not found")
        if supplier.status != "ACTIVE":
            raise BusinessRuleError("Supplier must be active")
        mappings = self.repository.mappings(session, mapping_ids)
        if len(mappings) != len(set(mapping_ids)):
            raise NotFoundError("Supplier ingredient mapping not found")
        ingredients = lock_ingredients(session, [m.ingredient_id for m in mappings.values()])
        mappings = self.repository.mappings(session, mapping_ids, lock=True)
        for mapping in mappings.values():
            if mapping.supplier_id != supplier_id:
                raise BusinessRuleError("All items must belong to the purchase order supplier")
            if not mapping.is_active:
                raise BusinessRuleError("Supplier ingredient mapping must be active")
            ingredient = ingredients[mapping.ingredient_id]
            for unit_id in (mapping.purchase_unit_id, ingredient.base_unit_id):
                unit = self.repository.unit(session, unit_id)
                if unit is None or not unit.is_active:
                    raise BusinessRuleError("Purchase and base units must be active")
            factor = exact_quantity(mapping.base_qty_per_purchase_unit)
            if factor <= 0:
                raise BusinessRuleError("Purchase unit conversion factor must be positive")
            if mapping.purchase_unit_id == ingredient.base_unit_id and factor != 1:
                raise BusinessRuleError("Identical purchase and base units require factor 1")
        return mappings

    def prepare_items(
        self,
        session: Session,
        supplier_id: int,
        inputs: list[PurchaseOrderItemInput],
    ) -> tuple[list[PurchaseOrderItem], Decimal]:
        ids = [line.supplier_ingredient_id for line in inputs]
        if len(ids) != len(set(ids)):
            raise BusinessRuleError("Each supplier ingredient may appear only once")
        mappings = self.active_mappings(session, supplier_id, ids)
        items = []
        subtotal = Decimal("0")
        for line in inputs:
            mapping = mappings[line.supplier_ingredient_id]
            quantity = exact_quantity(line.ordered_quantity)
            if quantity < mapping.minimum_order_qty:
                raise BusinessRuleError("Ordered quantity is below supplier minimum order quantity")
            # Refuse silent rounding/overflow of PostgreSQL's generated numeric
            # quantity. Generated columns themselves are never assigned.
            exact_quantity(quantity * mapping.base_qty_per_purchase_unit)
            amount = money(quantity * line.expected_unit_price)
            subtotal = money(subtotal + amount)
            items.append(
                PurchaseOrderItem(
                    supplier_ingredient_id=mapping.supplier_ingredient_id,
                    purchase_unit_id=mapping.purchase_unit_id,
                    ordered_quantity=quantity,
                    base_qty_per_purchase_unit=mapping.base_qty_per_purchase_unit,
                    expected_unit_price=money(line.expected_unit_price),
                )
            )
        return items, subtotal

    def create(self, session: Session, data: PurchaseOrderCreate) -> PurchaseOrderRead:
        with transaction(session):
            require_actor(session, data.created_by)
            items, subtotal = self.prepare_items(session, data.supplier_id, data.items)
            order = PurchaseOrder(
                purchase_order_number=data.purchase_order_number or f"PO-{uuid4().hex}",
                supplier_id=data.supplier_id,
                created_by=data.created_by,
                status="DRAFT",
                order_date=data.order_date,
                expected_delivery_date=data.expected_delivery_date,
                notes=data.notes,
                subtotal_amount=subtotal,
            )
            session.add(order)
            session.flush()
            for item in items:
                item.purchase_order_id = order.purchase_order_id
                session.add(item)
            session.flush()
            result = self.read(session, order)
        return result

    def update(
        self,
        session: Session,
        order_id: int,
        data: PurchaseOrderUpdate,
    ) -> PurchaseOrderRead:
        with transaction(session):
            order = self.require_order(session, order_id, lock=True)
            if order.status != "DRAFT":
                raise ConflictError("Only draft purchase orders may be edited")
            if self.repository.has_receipts(session, order_id):
                raise ConflictError("Purchase orders with receipts cannot be edited")
            changes = data.model_dump(exclude_unset=True, exclude={"items"})
            order_date = changes.get("order_date", order.order_date)
            delivery = changes.get("expected_delivery_date", order.expected_delivery_date)
            if delivery and delivery < order_date:
                raise BusinessRuleError("Expected delivery date cannot precede order date")
            if data.items is not None:
                items, subtotal = self.prepare_items(session, order.supplier_id, data.items)
                for item in self.repository.items(session, order_id):
                    session.delete(item)
                session.flush()
                for item in items:
                    item.purchase_order_id = order_id
                    session.add(item)
                order.subtotal_amount = subtotal
            for field, value in changes.items():
                setattr(order, field, value)
            session.flush()
            result = self.read(session, order)
        return result

    def transition(
        self,
        session: Session,
        order_id: int,
        data: PurchaseOrderTransition,
    ) -> PurchaseOrderRead:
        with transaction(session):
            order = self.require_order(session, order_id, lock=True)
            require_actor(session, data.actor_id)
            if order.status == data.status:
                return self.read(session, order)
            if data.status == "CANCELLED":
                if order.status not in {"DRAFT", "PENDING_APPROVAL", "APPROVED", "ORDERED"}:
                    raise ConflictError("Received purchase orders cannot be cancelled")
                if self.repository.has_receipts(session, order_id, confirmed_only=True):
                    raise ConflictError(
                        "Purchase orders with confirmed receipts cannot be cancelled"
                    )
                order.cancelled_at = datetime.now(UTC)
                order.cancellation_reason = data.cancellation_reason
            else:
                allowed = {
                    "DRAFT": "PENDING_APPROVAL",
                    "PENDING_APPROVAL": "APPROVED",
                    "APPROVED": "ORDERED",
                }
                if allowed.get(order.status) != data.status:
                    raise ConflictError(
                        f"Cannot change purchase order {order.status} to {data.status}"
                    )
                items = self.repository.items(session, order_id)
                if not items:
                    raise BusinessRuleError("Purchase order must contain at least one item")
                self.active_mappings(
                    session, order.supplier_id, [item.supplier_ingredient_id for item in items]
                )
                if data.status == "APPROVED":
                    order.approved_by = data.actor_id
            order.status = data.status
            session.flush()
            result = self.read(session, order)
        return result
