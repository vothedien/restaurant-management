from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class IngredientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ingredient_id: int
    ingredient_code: str
    ingredient_name: str
    base_unit_id: int
    manages_lot: bool
    default_shelf_life_days: int | None
    minimum_stock_qty: Decimal
    safety_stock_qty: Decimal
    status: str
    created_at: datetime
    updated_at: datetime


class IngredientListData(BaseModel):
    items: list[IngredientRead]
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
