from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text

from app.db.base import Base


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("subtotal_amount >= 0", name="ck_orders_subtotal"),
        CheckConstraint(
            "status IN ('OPEN', 'SENT', 'IN_PROGRESS', 'COMPLETED', 'PAID', 'CANCELLED')",
            name="ck_orders_status",
        ),
        CheckConstraint("sent_at IS NULL OR sent_at >= opened_at", name="ck_orders_sent_at"),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= opened_at", name="ck_orders_completed_at"
        ),
        CheckConstraint(
            "(status <> 'CANCELLED') OR "
            "(cancelled_at IS NOT NULL AND cancellation_reason IS NOT NULL)",
            name="ck_orders_cancellation",
        ),
    )

    order_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    order_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    table_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.dining_tables.table_id", ondelete="RESTRICT"),
        nullable=False,
    )
    opened_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.users.user_id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'OPEN'"))
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subtotal_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    cancelled_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.users.user_id", ondelete="SET NULL")
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list[OrderItem]] = relationship("OrderItem", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price"),
        CheckConstraint(
            "status IN ('PENDING', 'SENT', 'PREPARING', 'COMPLETED', 'CANCELLED')",
            name="ck_order_items_status",
        ),
        CheckConstraint(
            "(status <> 'CANCELLED') OR "
            "(cancelled_at IS NOT NULL AND cancellation_reason IS NOT NULL)",
            name="ck_order_items_cancellation",
        ),
    )

    order_item_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.orders.order_id", ondelete="CASCADE"), nullable=False
    )
    dish_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.dishes.dish_id", ondelete="RESTRICT"), nullable=False
    )
    recipe_version_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.recipe_versions.recipe_version_id", ondelete="RESTRICT"),
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), Computed("quantity * unit_price", persisted=True)
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'PENDING'")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.users.user_id", ondelete="SET NULL")
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(Text)

    order: Mapped[Order] = relationship("Order", back_populates="items")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payments_amount"),
        CheckConstraint(
            "payment_method IN ('CASH', 'CARD', 'BANK_TRANSFER', 'E_WALLET')",
            name="ck_payments_method",
        ),
    )

    payment_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    payment_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.orders.order_id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)
    received_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.users.user_id", ondelete="RESTRICT"), nullable=False
    )
    paid_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    notes: Mapped[str | None] = mapped_column(Text)

    order: Mapped[Order] = relationship("Order")
