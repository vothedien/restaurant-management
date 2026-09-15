from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator


class IngredientRequirement(BaseModel):
    ingredient_id: int
    base_quantity: Decimal


class ConsumptionMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stock_movement_id: int
    movement_number: str
    ingredient_id: int
    stock_lot_id: int | None
    quantity: Decimal
    occurred_at: datetime
    performed_by: int | None
    order_item_id: int | None

    @field_validator("occurred_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        # SQLite returns naive UTC on reload; keep first/replayed results equal.
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ConsumptionResult(BaseModel):
    order_item_id: int
    recipe_version_id: int
    already_consumed: bool
    requirements: list[IngredientRequirement]
    movements: list[ConsumptionMovementRead]
