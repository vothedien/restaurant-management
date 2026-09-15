from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.modules.inventory.stock_schemas import Id, InputModel, Quantity, Reason

StocktakeStatus = Literal["DRAFT", "IN_PROGRESS", "COMPLETED", "CANCELLED"]
StocktakeNumber = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)
]


class StocktakeCreate(InputModel):
    stocktake_number: StocktakeNumber | None = None
    created_by: Id
    notes: str | None = Field(default=None, max_length=2000)


class StocktakeStart(InputModel):
    stock_lot_ids: list[Id] = Field(min_length=1, max_length=1000)

    @field_validator("stock_lot_ids")
    @classmethod
    def unique_lots(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("Each stock lot must appear only once")
        return value


class StocktakeCount(InputModel):
    actual_quantity: Quantity
    # Existing DDL has no counted flag. A note records explicit verification even
    # when the count matches the snapshot; NULL remains reserved for uncounted.
    adjustment_reason: Reason


class StocktakeComplete(InputModel):
    completed_by: Id


class StocktakeItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stocktake_item_id: int
    stocktake_id: int
    stock_lot_id: int
    system_quantity: Decimal
    actual_quantity: Decimal
    variance_quantity: Decimal
    adjustment_reason: str | None
    counted: bool


class StocktakeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stocktake_id: int
    stocktake_number: str
    status: StocktakeStatus
    started_at: datetime | None
    completed_at: datetime | None
    created_by: int
    completed_by: int | None
    notes: str | None
    created_at: datetime

    @field_validator("started_at", "completed_at", "created_at")
    @classmethod
    def utc_timestamp(cls, value: datetime | None) -> datetime | None:
        # PostgreSQL retains UTC offsets; the offline SQLite adapter returns
        # naive UTC. Keep initial and repeated API responses identical in both.
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class StocktakeDetail(StocktakeRead):
    items: list[StocktakeItemRead]
