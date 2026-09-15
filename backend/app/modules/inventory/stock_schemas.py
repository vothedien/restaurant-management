from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Id = Annotated[int, Field(gt=0, le=9223372036854775807)]
Quantity = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=3)]
PositiveQuantity = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
LotStatus = Literal["ACTIVE", "DEPLETED", "EXPIRED", "BLOCKED"]
MovementType = Literal["RECEIPT", "CONSUMPTION", "ADJUSTMENT", "RETURN"]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StockIssue(InputModel):
    ingredient_id: Id
    quantity: PositiveQuantity
    unit_id: Id
    performed_by: Id
    reason: Reason


class StockAdjustment(InputModel):
    actual_quantity: Quantity
    performed_by: Id
    reason: Reason


class StockLotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stock_lot_id: int
    ingredient_id: int
    goods_receipt_item_id: int | None
    lot_code: str
    manufacture_date: date | None
    expiry_date: date | None
    received_quantity: Decimal
    current_quantity: Decimal
    unit_cost: Decimal
    status: LotStatus
    created_at: datetime


class StockMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stock_movement_id: int
    movement_number: str
    ingredient_id: int
    stock_lot_id: int | None
    movement_type: MovementType
    direction: Literal["IN", "OUT"]
    quantity: Decimal
    occurred_at: datetime
    performed_by: int | None
    order_item_id: int | None
    goods_receipt_item_id: int | None
    stocktake_item_id: int | None
    reason: str | None
    created_at: datetime

    @field_validator("occurred_at", "created_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class StockBalanceRead(BaseModel):
    ingredient_id: int
    ingredient_code: str
    ingredient_name: str
    base_unit_id: int
    current_quantity: Decimal
    available_quantity: Decimal
    unavailable_quantity: Decimal


class StockChangeRead(BaseModel):
    movements: list[StockMovementRead]
