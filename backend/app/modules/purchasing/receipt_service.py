from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.db.models.inventory import GoodsReceipt, GoodsReceiptItem, PurchaseOrder, StockLot
from app.modules.inventory.stock_common import (
    add_movement,
    database_errors,
    exact_quantity,
    money,
    require_actor,
    transaction,
    unit_cost,
)
from app.modules.purchasing.order_service import PurchaseOrderService
from app.modules.purchasing.receipt_repository import GoodsReceiptRepository
from app.modules.purchasing.receipt_schemas import (
    GoodsReceiptCreate,
    GoodsReceiptItemRead,
    GoodsReceiptRead,
)


class GoodsReceiptService:
    def __init__(self, repository: GoodsReceiptRepository | None = None) -> None:
        self.repository = repository or GoodsReceiptRepository()
        self.orders = PurchaseOrderService()

    def read(self, session: Session, receipt: GoodsReceipt) -> GoodsReceiptRead:
        values = {
            name: getattr(receipt, name)
            for name in GoodsReceiptRead.model_fields
            if name != "items"
        }
        return GoodsReceiptRead(
            **values,
            items=[
                GoodsReceiptItemRead.model_validate(item)
                for item in self.repository.items(session, receipt.goods_receipt_id)
            ],
        )

    def get(self, session: Session, receipt_id: int) -> GoodsReceiptRead:
        with database_errors(session):
            receipt = self.repository.get(session, receipt_id)
            if receipt is None:
                raise NotFoundError("Goods receipt not found")
            return self.read(session, receipt)

    def list(self, session: Session, **filters) -> tuple[list[GoodsReceiptRead], int]:
        with database_errors(session):
            if filters["date_from"] and filters["date_to"]:
                if filters["date_from"] > filters["date_to"]:
                    raise BusinessRuleError("Date range start cannot follow its end")
            receipts, total = self.repository.list(session, **filters)
            return [self.read(session, receipt) for receipt in receipts], total

    def lock_receipt(self, session: Session, receipt_id: int) -> tuple[PurchaseOrder, GoodsReceipt]:
        order_id = self.repository.order_id(session, receipt_id)
        if order_id is None:
            raise NotFoundError("Goods receipt not found")
        # Parent first: different receipts of the same PO must serialize before
        # aggregating confirmed quantities; receipt lock alone is insufficient.
        order = self.orders.require_order(session, order_id, lock=True)
        receipt = self.repository.get(session, receipt_id, lock=True)
        if receipt is None:
            raise NotFoundError("Goods receipt not found")
        return order, receipt

    @staticmethod
    def require_receivable(order: PurchaseOrder) -> None:
        if order.status not in {"ORDERED", "PARTIALLY_RECEIVED"}:
            raise ConflictError(
                "Only ordered or partially received purchase orders can receive goods"
            )

    def validate_lines(
        self,
        session: Session,
        order: PurchaseOrder,
        receipt_date: date,
        items: list[GoodsReceiptItem],
    ) -> dict[int, int]:
        if receipt_date > date.today():
            raise BusinessRuleError("Receipt date cannot be in the future")
        if receipt_date < order.order_date:
            raise BusinessRuleError("Receipt date cannot precede purchase order date")
        if not items:
            raise BusinessRuleError("Goods receipt must contain at least one item")
        order_items = {
            item.purchase_order_item_id: item
            for item in self.orders.repository.items(session, order.purchase_order_id)
        }
        if any(item.purchase_order_item_id not in order_items for item in items):
            raise BusinessRuleError("Receipt items must belong to the linked purchase order")
        mappings = self.orders.active_mappings(
            session,
            order.supplier_id,
            [order_items[item.purchase_order_item_id].supplier_ingredient_id for item in items],
        )
        received = self.orders.repository.received_quantities(session, order.purchase_order_id)
        current: dict[int, Decimal] = {}
        ingredients: dict[int, int] = {}
        lot_keys = set()
        for item in items:
            po_item = order_items[item.purchase_order_item_id]
            mapping = mappings[po_item.supplier_ingredient_id]
            unit = self.orders.repository.unit(session, po_item.purchase_unit_id)
            if unit is None or not unit.is_active:
                raise BusinessRuleError("The purchase order's snapshotted unit must be active")
            quantity = exact_quantity(item.received_quantity)
            if quantity <= 0:
                raise BusinessRuleError("Received quantities must be positive")
            base_quantity = exact_quantity(quantity * po_item.base_qty_per_purchase_unit)
            if base_quantity <= 0:
                raise BusinessRuleError("Received base quantity must be positive")
            if (
                item.purchase_unit_id != po_item.purchase_unit_id
                or item.base_quantity != base_quantity
            ):
                raise BusinessRuleError(
                    "Receipt unit and base quantity must match the order snapshot"
                )
            if item.actual_unit_price < 0:
                raise BusinessRuleError("Actual unit price cannot be negative")
            money(quantity * item.actual_unit_price)
            unit_cost(item.actual_unit_price / po_item.base_qty_per_purchase_unit)
            if item.manufacture_date and item.manufacture_date > receipt_date:
                raise BusinessRuleError("Manufacture date cannot follow receipt date")
            if item.expiry_date and item.expiry_date < receipt_date:
                raise BusinessRuleError("Goods must not be expired on the receipt date")
            current[item.purchase_order_item_id] = (
                current.get(item.purchase_order_item_id, Decimal("0")) + quantity
            )
            ingredients[item.purchase_order_item_id] = mapping.ingredient_id
            key = (mapping.ingredient_id, item.lot_code)
            if key in lot_keys:
                raise BusinessRuleError("Each ingredient lot code may appear only once per receipt")
            lot_keys.add(key)
        for item_id, quantity in current.items():
            if (
                received.get(item_id, Decimal("0")) + quantity
                > order_items[item_id].ordered_quantity
            ):
                raise ConflictError("Receipt would exceed the purchase order's remaining quantity")
        return ingredients

    def create(self, session: Session, data: GoodsReceiptCreate) -> GoodsReceiptRead:
        with transaction(session):
            require_actor(session, data.received_by)
            order = self.orders.require_order(session, data.purchase_order_id, lock=True)
            self.require_receivable(order)
            order_items = {
                item.purchase_order_item_id: item
                for item in self.orders.repository.items(session, order.purchase_order_id)
            }
            items = []
            for line in data.items:
                po_item = order_items.get(line.purchase_order_item_id)
                if po_item is None:
                    raise BusinessRuleError(
                        "Receipt items must belong to the linked purchase order"
                    )
                values = line.model_dump()
                values["lot_code"] = line.lot_code or f"GR-{uuid4().hex}"
                items.append(
                    GoodsReceiptItem(
                        **values,
                        purchase_unit_id=po_item.purchase_unit_id,
                        base_quantity=exact_quantity(
                            line.received_quantity * po_item.base_qty_per_purchase_unit,
                        ),
                    )
                )
            self.validate_lines(session, order, data.receipt_date, items)
            receipt = GoodsReceipt(
                receipt_number=data.receipt_number or f"GR-{uuid4().hex}",
                purchase_order_id=order.purchase_order_id,
                receipt_date=data.receipt_date,
                supplier_document_no=data.supplier_document_no,
                received_by=data.received_by,
                notes=data.notes,
                status="DRAFT",
            )
            session.add(receipt)
            session.flush()
            for item in items:
                item.goods_receipt_id = receipt.goods_receipt_id
                session.add(item)
            session.flush()
            result = self.read(session, receipt)
        return result

    def confirm(self, session: Session, receipt_id: int) -> GoodsReceiptRead:
        with transaction(session):
            order, receipt = self.lock_receipt(session, receipt_id)
            if receipt.status == "CONFIRMED":
                return self.read(session, receipt)
            if receipt.status != "DRAFT":
                raise ConflictError("Only draft goods receipts can be confirmed")
            self.require_receivable(order)
            require_actor(session, receipt.received_by)
            items = self.repository.items(session, receipt_id)
            for item in items:
                if not item.lot_code:
                    item.lot_code = f"GR-{uuid4().hex}"
            ingredients = self.validate_lines(session, order, receipt.receipt_date, items)
            keys = {(ingredients[item.purchase_order_item_id], item.lot_code) for item in items}
            if self.repository.existing_lots(session, keys):
                # A lot has exactly one source receipt item in the existing
                # schema. Never merge deliveries and lose that provenance.
                raise ConflictError(
                    "Ingredient lot code already exists; use a new internal lot code"
                )
            order_items = {
                item.purchase_order_item_id: item
                for item in self.orders.repository.items(session, order.purchase_order_id)
            }
            for item in items:
                po_item = order_items[item.purchase_order_item_id]
                lot = StockLot(
                    ingredient_id=ingredients[item.purchase_order_item_id],
                    goods_receipt_item_id=item.goods_receipt_item_id,
                    lot_code=item.lot_code,
                    manufacture_date=item.manufacture_date,
                    expiry_date=item.expiry_date,
                    received_quantity=item.base_quantity,
                    current_quantity=item.base_quantity,
                    unit_cost=unit_cost(
                        item.actual_unit_price / po_item.base_qty_per_purchase_unit
                    ),
                    status="EXPIRED"
                    if item.expiry_date and item.expiry_date < date.today()
                    else "ACTIVE",
                )
                session.add(lot)
                session.flush()
                add_movement(
                    session,
                    lot,
                    movement_type="RECEIPT",
                    direction="IN",
                    quantity=item.base_quantity,
                    performed_by=receipt.received_by,
                    goods_receipt_item_id=item.goods_receipt_item_id,
                    reason=f"Goods receipt {receipt.receipt_number}",
                )
            receipt.status = "CONFIRMED"
            session.flush()
            received = self.orders.repository.received_quantities(session, order.purchase_order_id)
            complete = all(
                received.get(item_id, Decimal("0")) == item.ordered_quantity
                for item_id, item in order_items.items()
            )
            order.status = "RECEIVED" if complete else "PARTIALLY_RECEIVED"
            session.flush()
            result = self.read(session, receipt)
        return result

    def cancel(self, session: Session, receipt_id: int) -> GoodsReceiptRead:
        with transaction(session):
            _, receipt = self.lock_receipt(session, receipt_id)
            if receipt.status == "CONFIRMED":
                raise ConflictError("Confirmed goods receipts cannot be cancelled")
            receipt.status = "CANCELLED"
            session.flush()
            result = self.read(session, receipt)
        return result
