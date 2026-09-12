from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.inventory.schemas import IngredientStatus, UnitSummary

RecipeStatus = Literal["DRAFT", "ACTIVE", "INACTIVE", "EXPIRED"]


class RecipeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effective_from: date | None = None
    effective_to: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValueError("effective_to must be on or after effective_from")
        return self


class RecipeCreate(RecipeUpdate):
    dish_id: int = Field(gt=0)


class RecipeItemWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ingredient_id: int = Field(gt=0)
    unit_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)


class RecipeItemsReplace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[RecipeItemWrite] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_ingredients(self) -> Self:
        if len({item.ingredient_id for item in self.items}) != len(self.items):
            raise ValueError("Recipe ingredients must be unique")
        return self


class DishSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dish_id: int
    dish_code: str
    dish_name: str
    status: Literal["ACTIVE", "INACTIVE", "SOLD_OUT"]


class IngredientSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ingredient_id: int
    ingredient_code: str
    ingredient_name: str
    base_unit_id: int
    status: IngredientStatus
    base_unit: UnitSummary


class RecipeItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recipe_item_id: int
    recipe_version_id: int
    ingredient_id: int
    unit_id: int
    quantity: Decimal
    base_quantity: Decimal
    ingredient: IngredientSummary
    unit: UnitSummary


class RecipeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recipe_version_id: int
    dish_id: int
    version_no: int
    status: RecipeStatus
    effective_from: date | None
    effective_to: date | None
    notes: str | None
    created_by: int | None
    created_at: datetime
    dish: DishSummary


class RecipeDetail(RecipeRead):
    items: list[RecipeItemRead]


class RecipeListData(BaseModel):
    items: list[RecipeRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
