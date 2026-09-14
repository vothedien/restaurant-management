import re
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.inventory.schemas import IngredientStatus, UnitSummary

SupplierStatus = Literal["ACTIVE", "INACTIVE", "SUSPENDED"]
MAX_BIGINT = 9223372036854775807
MAX_INTEGER = 2147483647


class SupplierCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_code: str = Field(min_length=1, max_length=40)
    supplier_name: str = Field(min_length=1, max_length=180)
    contact_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=150)
    address: str | None = None
    tax_code: str | None = Field(default=None, max_length=30)
    status: SupplierStatus = "ACTIVE"

    @field_validator("supplier_code", "status", mode="before")
    @classmethod
    def normalize_code_and_status(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("supplier_name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("contact_name", "phone", "email", "address", "tax_code", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        return (value.strip() or None) if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is not None and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) is None:
            raise ValueError("email must be a valid email address")
        return value


class SupplierUpdate(SupplierCreate):
    supplier_code: str | None = Field(default=None, min_length=1, max_length=40)
    supplier_name: str | None = Field(default=None, min_length=1, max_length=180)
    status: SupplierStatus | None = None

    @field_validator("supplier_code", "supplier_name", "status", mode="before")
    @classmethod
    def reject_null_required_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("This field cannot be null")
        return value


class SupplierSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    supplier_id: int
    supplier_code: str
    supplier_name: str
    status: SupplierStatus


class SupplierRead(SupplierSummary):
    contact_name: str | None
    phone: str | None
    email: str | None
    address: str | None
    tax_code: str | None
    created_at: datetime
    updated_at: datetime


class SupplierListData(BaseModel):
    items: list[SupplierRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class _SupplierIngredientInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_sku: str | None = Field(default=None, max_length=80)
    purchase_unit_id: int = Field(gt=0, le=MAX_BIGINT)
    base_qty_per_purchase_unit: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    lead_time_days: int = Field(default=0, ge=0, le=MAX_INTEGER)
    minimum_order_qty: Decimal = Field(default=Decimal("1"), gt=0, max_digits=14, decimal_places=3)
    latest_unit_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    is_preferred: bool = False
    is_active: bool = True

    @field_validator("supplier_sku", mode="before")
    @classmethod
    def normalize_sku(cls, value: object) -> object:
        return (value.strip() or None) if isinstance(value, str) else value


class SupplierIngredientCreate(_SupplierIngredientInput):
    supplier_id: int = Field(gt=0, le=MAX_BIGINT)
    ingredient_id: int = Field(gt=0, le=MAX_BIGINT)


class SupplierIngredientUpdate(_SupplierIngredientInput):
    purchase_unit_id: int | None = Field(default=None, gt=0, le=MAX_BIGINT)
    base_qty_per_purchase_unit: Decimal | None = Field(
        default=None, gt=0, max_digits=14, decimal_places=3
    )
    lead_time_days: int | None = Field(default=None, ge=0, le=MAX_INTEGER)
    minimum_order_qty: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=3)
    is_preferred: bool | None = None
    is_active: bool | None = None

    @field_validator(
        "purchase_unit_id",
        "base_qty_per_purchase_unit",
        "lead_time_days",
        "minimum_order_qty",
        "is_preferred",
        "is_active",
        mode="before",
    )
    @classmethod
    def reject_null_required_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("This field cannot be null")
        return value


class IngredientSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ingredient_id: int
    ingredient_code: str
    ingredient_name: str
    base_unit_id: int
    status: IngredientStatus


class SupplierIngredientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    supplier_ingredient_id: int
    supplier_id: int
    ingredient_id: int
    supplier_sku: str | None
    purchase_unit_id: int
    base_qty_per_purchase_unit: Decimal
    lead_time_days: int
    minimum_order_qty: Decimal
    latest_unit_price: Decimal | None
    is_preferred: bool
    is_active: bool
    supplier: SupplierSummary
    ingredient: IngredientSummary
    purchase_unit: UnitSummary


class SupplierIngredientListData(BaseModel):
    items: list[SupplierIngredientRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
