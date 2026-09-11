from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

UnitDimension = Literal["MASS", "VOLUME", "COUNT", "LENGTH", "OTHER"]
IngredientStatus = Literal["ACTIVE", "INACTIVE"]


class UnitCreate(BaseModel):
    unit_code: str = Field(min_length=1, max_length=20)
    unit_name: str = Field(min_length=1, max_length=80)
    dimension: UnitDimension
    is_active: bool = True

    @field_validator("unit_code", mode="before")
    @classmethod
    def normalize_unit_code(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("unit_code must be a string")
        normalized = "".join(value.split()).upper()
        if not normalized:
            raise ValueError("unit_code cannot be blank")
        return normalized

    @field_validator("unit_name")
    @classmethod
    def normalize_unit_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("unit_name cannot be blank")
        return normalized

    @field_validator("dimension", mode="before")
    @classmethod
    def normalize_dimension(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class UnitUpdate(BaseModel):
    unit_code: str | None = Field(default=None, min_length=1, max_length=20)
    unit_name: str | None = Field(default=None, min_length=1, max_length=80)
    dimension: UnitDimension | None = None
    is_active: bool | None = None

    @field_validator("unit_code", mode="before")
    @classmethod
    def normalize_unit_code(cls, value: object) -> str:
        return UnitCreate.normalize_unit_code(value)

    @field_validator("unit_name")
    @classmethod
    def normalize_unit_name(cls, value: str) -> str:
        return UnitCreate.normalize_unit_name(value)

    @field_validator("dimension", mode="before")
    @classmethod
    def normalize_dimension(cls, value: object) -> object:
        return UnitCreate.normalize_dimension(value)


class UnitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    unit_id: int
    unit_code: str
    unit_name: str
    dimension: UnitDimension
    is_active: bool


class UnitListData(BaseModel):
    items: list[UnitRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class UnitConversionCreate(BaseModel):
    from_unit_id: int = Field(gt=0)
    to_unit_id: int = Field(gt=0)
    factor: Decimal = Field(gt=0, max_digits=18, decimal_places=6)


class UnitConversionUpdate(BaseModel):
    from_unit_id: int | None = Field(default=None, gt=0)
    to_unit_id: int | None = Field(default=None, gt=0)
    factor: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=6)


class UnitSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    unit_id: int
    unit_code: str
    unit_name: str
    dimension: UnitDimension
    is_active: bool


class UnitConversionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conversion_id: int
    from_unit_id: int
    to_unit_id: int
    factor: Decimal
    from_unit: UnitSummary
    to_unit: UnitSummary


class UnitConversionListData(BaseModel):
    items: list[UnitConversionRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class IngredientCreate(BaseModel):
    ingredient_code: str = Field(min_length=1, max_length=40)
    ingredient_name: str = Field(min_length=1, max_length=150)
    base_unit_id: int = Field(gt=0)
    manages_lot: bool = True
    default_shelf_life_days: int | None = Field(default=None, ge=0)
    minimum_stock_qty: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=3)
    safety_stock_qty: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=3)
    status: IngredientStatus = "ACTIVE"

    @field_validator("ingredient_code", mode="before")
    @classmethod
    def normalize_ingredient_code(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("ingredient_code must be a string")
        normalized = "".join(value.split()).upper()
        if not normalized:
            raise ValueError("ingredient_code cannot be blank")
        return normalized

    @field_validator("ingredient_name")
    @classmethod
    def normalize_ingredient_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("ingredient_name cannot be blank")
        return normalized

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class IngredientUpdate(BaseModel):
    ingredient_code: str | None = Field(default=None, min_length=1, max_length=40)
    ingredient_name: str | None = Field(default=None, min_length=1, max_length=150)
    base_unit_id: int | None = Field(default=None, gt=0)
    manages_lot: bool | None = None
    default_shelf_life_days: int | None = Field(default=None, ge=0)
    minimum_stock_qty: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=3)
    safety_stock_qty: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=3)
    status: IngredientStatus | None = None

    @field_validator("ingredient_code", mode="before")
    @classmethod
    def normalize_ingredient_code(cls, value: object) -> str:
        return IngredientCreate.normalize_ingredient_code(value)

    @field_validator("ingredient_name")
    @classmethod
    def normalize_ingredient_name(cls, value: str) -> str:
        return IngredientCreate.normalize_ingredient_name(value)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: object) -> object:
        return IngredientCreate.normalize_status(value)


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
    status: IngredientStatus
    created_at: datetime
    updated_at: datetime
    base_unit: UnitSummary


class IngredientListData(BaseModel):
    items: list[IngredientRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
