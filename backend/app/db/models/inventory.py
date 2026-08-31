from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text

from app.db.base import Base


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE', 'SUSPENDED')", name="ck_suppliers_status"
        ),
    )

    supplier_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    supplier_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    supplier_name: Mapped[str] = mapped_column(String(180), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(150))
    address: Mapped[str | None] = mapped_column(Text)
    tax_code: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'ACTIVE'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class SupplierIngredient(Base):
    __tablename__ = "supplier_ingredients"
    __table_args__ = (
        UniqueConstraint(
            "supplier_id", "ingredient_id", name="uq_supplier_ingredients_supplier_ingredient"
        ),
        CheckConstraint("base_qty_per_purchase_unit > 0", name="ck_supplier_ingredients_base_qty"),
        CheckConstraint("lead_time_days >= 0", name="ck_supplier_ingredients_lead_time"),
        CheckConstraint("minimum_order_qty > 0", name="ck_supplier_ingredients_minimum_order"),
        CheckConstraint(
            "latest_unit_price IS NULL OR latest_unit_price >= 0",
            name="ck_supplier_ingredients_price",
        ),
    )

    supplier_ingredient_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    supplier_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.suppliers.supplier_id", ondelete="RESTRICT"),
        nullable=False,
    )
    ingredient_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.ingredients.ingredient_id", ondelete="RESTRICT"),
        nullable=False,
    )
    supplier_sku: Mapped[str | None] = mapped_column(String(80))
    purchase_unit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.units.unit_id", ondelete="RESTRICT"), nullable=False
    )
    base_qty_per_purchase_unit: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    minimum_order_qty: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, server_default=text("1")
    )
    latest_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    is_preferred: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    supplier: Mapped[Supplier] = relationship("Supplier")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'ORDERED', "
            "'PARTIALLY_RECEIVED', 'RECEIVED', 'CANCELLED')",
            name="ck_purchase_orders_status",
        ),
        CheckConstraint(
            "expected_delivery_date IS NULL OR expected_delivery_date >= order_date",
            name="ck_purchase_orders_delivery_date",
        ),
        CheckConstraint("subtotal_amount >= 0", name="ck_purchase_orders_subtotal"),
        CheckConstraint(
            "status <> 'CANCELLED' OR "
            "(cancelled_at IS NOT NULL AND cancellation_reason IS NOT NULL)",
            name="ck_purchase_orders_cancelled",
        ),
    )

    purchase_order_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    purchase_order_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    supplier_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.suppliers.supplier_id", ondelete="RESTRICT"),
        nullable=False,
    )
    proposal_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.replenishment_proposals.proposal_id", ondelete="SET NULL"),
    )
    status: Mapped[str] = mapped_column(String(25), nullable=False, server_default=text("'DRAFT'"))
    order_date: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=text("CURRENT_DATE")
    )
    expected_delivery_date: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.users.user_id", ondelete="RESTRICT"), nullable=False
    )
    approved_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.users.user_id", ondelete="SET NULL")
    )
    subtotal_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    supplier: Mapped[Supplier] = relationship("Supplier")
    items: Mapped[list[PurchaseOrderItem]] = relationship(
        "PurchaseOrderItem", back_populates="purchase_order"
    )


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"
    __table_args__ = (
        UniqueConstraint(
            "purchase_order_id",
            "supplier_ingredient_id",
            name="uq_purchase_order_items_order_supplier_ingredient",
        ),
        CheckConstraint("ordered_quantity > 0", name="ck_purchase_order_items_quantity"),
        CheckConstraint("base_qty_per_purchase_unit > 0", name="ck_purchase_order_items_base_qty"),
        CheckConstraint("expected_unit_price >= 0", name="ck_purchase_order_items_price"),
    )

    purchase_order_item_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.purchase_orders.purchase_order_id", ondelete="CASCADE"),
        nullable=False,
    )
    supplier_ingredient_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "restaurant_ai.supplier_ingredients.supplier_ingredient_id", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    purchase_unit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.units.unit_id", ondelete="RESTRICT"), nullable=False
    )
    ordered_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    base_qty_per_purchase_unit: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    ordered_base_qty: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), Computed("ordered_quantity * base_qty_per_purchase_unit", persisted=True)
    )
    expected_unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), Computed("ordered_quantity * expected_unit_price", persisted=True)
    )

    purchase_order: Mapped[PurchaseOrder] = relationship("PurchaseOrder", back_populates="items")


class GoodsReceipt(Base):
    __tablename__ = "goods_receipts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')", name="ck_goods_receipts_status"
        ),
    )

    goods_receipt_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    receipt_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    purchase_order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.purchase_orders.purchase_order_id", ondelete="RESTRICT"),
        nullable=False,
    )
    receipt_date: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=text("CURRENT_DATE")
    )
    supplier_document_no: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'DRAFT'"))
    received_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.users.user_id", ondelete="RESTRICT"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    items: Mapped[list[GoodsReceiptItem]] = relationship(
        "GoodsReceiptItem", back_populates="goods_receipt"
    )


class GoodsReceiptItem(Base):
    __tablename__ = "goods_receipt_items"
    __table_args__ = (
        CheckConstraint("received_quantity > 0", name="ck_goods_receipt_items_received_qty"),
        CheckConstraint("base_quantity > 0", name="ck_goods_receipt_items_base_qty"),
        CheckConstraint("actual_unit_price >= 0", name="ck_goods_receipt_items_price"),
        CheckConstraint(
            "expiry_date IS NULL OR manufacture_date IS NULL OR expiry_date >= manufacture_date",
            name="ck_goods_receipt_items_dates",
        ),
    )

    goods_receipt_item_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    goods_receipt_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.goods_receipts.goods_receipt_id", ondelete="CASCADE"),
        nullable=False,
    )
    purchase_order_item_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "restaurant_ai.purchase_order_items.purchase_order_item_id", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    purchase_unit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.units.unit_id", ondelete="RESTRICT"), nullable=False
    )
    base_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    actual_unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), Computed("received_quantity * actual_unit_price", persisted=True)
    )
    lot_code: Mapped[str | None] = mapped_column(String(80))
    manufacture_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)

    goods_receipt: Mapped[GoodsReceipt] = relationship("GoodsReceipt", back_populates="items")


class StockLot(Base):
    __tablename__ = "stock_lots"
    __table_args__ = (
        UniqueConstraint("ingredient_id", "lot_code", name="uq_stock_lots_ingredient_lot"),
        CheckConstraint("received_quantity > 0", name="ck_stock_lots_received_qty"),
        CheckConstraint(
            "current_quantity >= 0 AND current_quantity <= received_quantity",
            name="ck_stock_lots_current_qty",
        ),
        CheckConstraint("unit_cost >= 0", name="ck_stock_lots_unit_cost"),
        CheckConstraint(
            "expiry_date IS NULL OR manufacture_date IS NULL OR expiry_date >= manufacture_date",
            name="ck_stock_lots_dates",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'DEPLETED', 'EXPIRED', 'BLOCKED')", name="ck_stock_lots_status"
        ),
    )

    stock_lot_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.ingredients.ingredient_id", ondelete="RESTRICT"),
        nullable=False,
    )
    goods_receipt_item_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.goods_receipt_items.goods_receipt_item_id", ondelete="RESTRICT"),
        unique=True,
    )
    lot_code: Mapped[str] = mapped_column(String(80), nullable=False)
    manufacture_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    current_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'ACTIVE'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class Stocktake(Base):
    __tablename__ = "stocktakes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')",
            name="ck_stocktakes_status",
        ),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="ck_stocktakes_dates",
        ),
        CheckConstraint(
            "status <> 'COMPLETED' OR (completed_at IS NOT NULL AND completed_by IS NOT NULL)",
            name="ck_stocktakes_completed",
        ),
    )

    stocktake_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    stocktake_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'DRAFT'"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.users.user_id", ondelete="RESTRICT"), nullable=False
    )
    completed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.users.user_id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class StocktakeItem(Base):
    __tablename__ = "stocktake_items"
    __table_args__ = (
        UniqueConstraint("stocktake_id", "stock_lot_id", name="uq_stocktake_items_stocktake_lot"),
        CheckConstraint("system_quantity >= 0", name="ck_stocktake_items_system_qty"),
        CheckConstraint("actual_quantity >= 0", name="ck_stocktake_items_actual_qty"),
        CheckConstraint(
            "actual_quantity = system_quantity OR adjustment_reason IS NOT NULL",
            name="ck_stocktake_items_adjustment_reason",
        ),
    )

    stocktake_item_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    stocktake_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.stocktakes.stocktake_id", ondelete="CASCADE"),
        nullable=False,
    )
    stock_lot_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.stock_lots.stock_lot_id", ondelete="RESTRICT"),
        nullable=False,
    )
    system_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    actual_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    variance_quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), Computed("actual_quantity - system_quantity", persisted=True)
    )
    adjustment_reason: Mapped[str | None] = mapped_column(Text)


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint(
            "movement_type IN ('RECEIPT', 'CONSUMPTION', 'ADJUSTMENT', 'RETURN')",
            name="ck_stock_movements_type",
        ),
        CheckConstraint("direction IN ('IN', 'OUT')", name="ck_stock_movements_direction"),
        CheckConstraint("quantity > 0", name="ck_stock_movements_quantity"),
    )

    stock_movement_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    movement_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    ingredient_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.ingredients.ingredient_id", ondelete="RESTRICT"),
        nullable=False,
    )
    stock_lot_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.stock_lots.stock_lot_id", ondelete="RESTRICT")
    )
    movement_type: Mapped[str] = mapped_column(String(25), nullable=False)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    performed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.users.user_id", ondelete="SET NULL")
    )
    order_item_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.order_items.order_item_id", ondelete="SET NULL")
    )
    goods_receipt_item_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.goods_receipt_items.goods_receipt_item_id", ondelete="SET NULL"),
    )
    stocktake_item_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.stocktake_items.stocktake_item_id", ondelete="SET NULL"),
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
