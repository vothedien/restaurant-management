from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.purchasing.order_schemas import Price, Quantity, ResourceId

ReceiptStatus = Literal["DRAFT", "CONFIRMED", "CANCELLED"]


class GoodsReceiptItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    purchase_order_item_id: ResourceId
    received_quantity: Quantity
    actual_unit_price: Price
    lot_code: str | None = Field(default=None, min_length=1, max_length=80)
    manufacture_date: date | None = None
    expiry_date: date | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "GoodsReceiptItemInput":
        if self.expiry_date and self.manufacture_date and self.expiry_date < self.manufacture_date:
            raise ValueError("Expiry date cannot precede manufacture date")
        return self


class GoodsReceiptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    receipt_number: str | None = Field(default=None, min_length=1, max_length=40)
    purchase_order_id: ResourceId
    receipt_date: date = Field(default_factory=date.today)
    supplier_document_no: str | None = Field(default=None, max_length=80)
    received_by: ResourceId
    notes: str | None = None
    items: list[GoodsReceiptItemInput] = Field(min_length=1, max_length=200)


class GoodsReceiptItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    goods_receipt_item_id: int
    purchase_order_item_id: int
    received_quantity: Decimal
    purchase_unit_id: int
    base_quantity: Decimal
    actual_unit_price: Decimal
    line_amount: Decimal
    lot_code: str | None
    manufacture_date: date | None
    expiry_date: date | None


class GoodsReceiptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    goods_receipt_id: int
    receipt_number: str
    purchase_order_id: int
    receipt_date: date
    supplier_document_no: str | None
    status: ReceiptStatus
    received_by: int
    notes: str | None
    created_at: datetime
    items: list[GoodsReceiptItemRead]
