from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text

from app.db.base import Base


class Unit(Base):
    __tablename__ = "units"
    __table_args__ = (
        CheckConstraint(
            "dimension IN ('MASS', 'VOLUME', 'COUNT', 'LENGTH', 'OTHER')", name="ck_units_dimension"
        ),
    )

    unit_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    unit_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    unit_name: Mapped[str] = mapped_column(String(80), nullable=False)
    dimension: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class UnitConversion(Base):
    __tablename__ = "unit_conversions"
    __table_args__ = (
        UniqueConstraint("from_unit_id", "to_unit_id", name="uq_unit_conversions_pair"),
        CheckConstraint("from_unit_id <> to_unit_id", name="ck_unit_conversions_different_units"),
        CheckConstraint("factor > 0", name="ck_unit_conversions_factor_positive"),
    )

    conversion_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    from_unit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.units.unit_id", ondelete="RESTRICT"), nullable=False
    )
    to_unit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.units.unit_id", ondelete="RESTRICT"), nullable=False
    )
    factor: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    from_unit: Mapped[Unit] = relationship("Unit", foreign_keys=[from_unit_id])
    to_unit: Mapped[Unit] = relationship("Unit", foreign_keys=[to_unit_id])


class Ingredient(Base):
    __tablename__ = "ingredients"
    __table_args__ = (
        CheckConstraint(
            "default_shelf_life_days IS NULL OR default_shelf_life_days >= 0",
            name="ck_ingredients_shelf_life",
        ),
        CheckConstraint("minimum_stock_qty >= 0", name="ck_ingredients_minimum_stock"),
        CheckConstraint("safety_stock_qty >= 0", name="ck_ingredients_safety_stock"),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_ingredients_status"),
    )

    ingredient_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ingredient_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    ingredient_name: Mapped[str] = mapped_column(String(150), nullable=False)
    base_unit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.units.unit_id", ondelete="RESTRICT"), nullable=False
    )
    manages_lot: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    default_shelf_life_days: Mapped[int | None] = mapped_column(Integer)
    minimum_stock_qty: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, server_default=text("0")
    )
    safety_stock_qty: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, server_default=text("0")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'ACTIVE'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    base_unit: Mapped[Unit] = relationship("Unit", foreign_keys=[base_unit_id])


class DiningTable(Base):
    __tablename__ = "dining_tables"
    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_dining_tables_capacity"),
        CheckConstraint(
            "status IN ('AVAILABLE', 'OCCUPIED', 'RESERVED', 'INACTIVE')",
            name="ck_dining_tables_status",
        ),
    )

    table_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    table_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    table_name: Mapped[str | None] = mapped_column(String(80))
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'AVAILABLE'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class MenuCategory(Base):
    __tablename__ = "menu_categories"
    __table_args__ = (
        CheckConstraint("display_order >= 0", name="ck_menu_categories_display_order"),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_menu_categories_status"),
    )

    category_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    category_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    category_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'ACTIVE'"))

    dishes: Mapped[list[Dish]] = relationship("Dish", back_populates="category")


class Dish(Base):
    __tablename__ = "dishes"
    __table_args__ = (
        CheckConstraint("selling_price >= 0", name="ck_dishes_selling_price"),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE', 'SOLD_OUT')", name="ck_dishes_status"),
    )

    dish_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    dish_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    dish_name: Mapped[str] = mapped_column(String(150), nullable=False)
    category_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.menu_categories.category_id", ondelete="RESTRICT"),
        nullable=False,
    )
    selling_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'ACTIVE'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    category: Mapped[MenuCategory] = relationship("MenuCategory", back_populates="dishes")
    recipe_versions: Mapped[list[RecipeVersion]] = relationship(
        "RecipeVersion", back_populates="dish"
    )


class RecipeVersion(Base):
    __tablename__ = "recipe_versions"
    __table_args__ = (
        UniqueConstraint("dish_id", "version_no", name="uq_recipe_versions_dish_version"),
        CheckConstraint("version_no > 0", name="ck_recipe_versions_version_no"),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_recipe_versions_dates",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'INACTIVE', 'EXPIRED')", name="ck_recipe_versions_status"
        ),
    )

    recipe_version_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    dish_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.dishes.dish_id", ondelete="RESTRICT"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'DRAFT'"))
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.users.user_id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    dish: Mapped[Dish] = relationship("Dish", back_populates="recipe_versions")


class RecipeItem(Base):
    __tablename__ = "recipe_items"
    __table_args__ = (
        UniqueConstraint(
            "recipe_version_id", "ingredient_id", name="uq_recipe_items_recipe_ingredient"
        ),
        CheckConstraint("quantity > 0", name="ck_recipe_items_quantity"),
        CheckConstraint("base_quantity > 0", name="ck_recipe_items_base_quantity"),
    )

    recipe_item_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    recipe_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.recipe_versions.recipe_version_id", ondelete="CASCADE"),
        nullable=False,
    )
    ingredient_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.ingredients.ingredient_id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.units.unit_id", ondelete="RESTRICT"), nullable=False
    )
    base_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)

    recipe_version: Mapped[RecipeVersion] = relationship("RecipeVersion")
    ingredient: Mapped[Ingredient] = relationship("Ingredient")
    unit: Mapped[Unit] = relationship("Unit")
