from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.purchasing.schemas import MAX_BIGINT

ResourceId = Annotated[int, Field(gt=0, le=MAX_BIGINT)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
Price = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
PurchaseOrderStatus = Literal[
    "DRAFT",
    "PENDING_APPROVAL",
    "APPROVED",
    "ORDERED",
    "PARTIALLY_RECEIVED",
    "RECEIVED",
    "CANCELLED",
]


class PurchaseOrderItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_ingredient_id: ResourceId
    ordered_quantity: Quantity
    # The caller supplies the agreed price; a supplier's latest/demo price is
    # deliberately not a fallback for a commercial purchase.
    expected_unit_price: Price


class PurchaseOrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    purchase_order_number: str | None = Field(default=None, min_length=1, max_length=40)
    supplier_id: ResourceId
    created_by: ResourceId
    order_date: date = Field(default_factory=date.today)
    expected_delivery_date: date | None = None
    notes: str | None = None
    items: list[PurchaseOrderItemInput] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_dates(self) -> "PurchaseOrderCreate":
        if self.expected_delivery_date and self.expected_delivery_date < self.order_date:
            raise ValueError("Expected delivery date cannot precede order date")
        return self


class PurchaseOrderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    order_date: date | None = None
    expected_delivery_date: date | None = None
    notes: str | None = None
    items: list[PurchaseOrderItemInput] | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("order_date", "items", mode="before")
    @classmethod
    def reject_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("This field cannot be null")
        return value


class PurchaseOrderTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: Literal["PENDING_APPROVAL", "APPROVED", "ORDERED", "CANCELLED"]
    actor_id: ResourceId
    cancellation_reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_reason(self) -> "PurchaseOrderTransition":
        if self.status == "CANCELLED" and not self.cancellation_reason:
            raise ValueError("Cancellation reason is required")
        return self


class PurchaseOrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    purchase_order_item_id: int
    supplier_ingredient_id: int
    purchase_unit_id: int
    ordered_quantity: Decimal
    base_qty_per_purchase_unit: Decimal
    ordered_base_qty: Decimal
    expected_unit_price: Decimal
    line_amount: Decimal
    received_quantity: Decimal = Decimal("0")
    remaining_quantity: Decimal = Decimal("0")


class PurchaseOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    purchase_order_id: int
    purchase_order_number: str
    supplier_id: int
    status: PurchaseOrderStatus
    order_date: date
    expected_delivery_date: date | None
    created_by: int
    approved_by: int | None
    subtotal_amount: Decimal
    notes: str | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    created_at: datetime
    items: list[PurchaseOrderItemRead]
