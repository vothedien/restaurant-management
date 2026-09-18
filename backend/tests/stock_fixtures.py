"""Offline workflow fixtures. Only a cloned, in-memory schema is created."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, Column, Index, Integer, MetaData, Table, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.core.config import Settings
from app.db.models.catalog import (
    DiningTable,
    Dish,
    Ingredient,
    MenuCategory,
    RecipeItem,
    RecipeVersion,
    Unit,
    UnitConversion,
)
from app.db.models.inventory import (
    GoodsReceipt,
    GoodsReceiptItem,
    PurchaseOrder,
    PurchaseOrderItem,
    StockLot,
    StockMovement,
    Stocktake,
    StocktakeItem,
    Supplier,
    SupplierIngredient,
)
from app.db.models.rbac import User
from app.db.models.sales import Order, OrderItem
from app.db.session import get_db
from tests.inventory_auth_fixtures import add_rbac_tables, authenticate_client, seed_inventory_users


def workflow_metadata() -> MetaData:
    metadata = MetaData()
    # The unused proposal FK resolves to a test-only stub; no AI tables are needed.
    Table(
        "replenishment_proposals",
        metadata,
        Column("proposal_id", Integer, primary_key=True),
        schema="restaurant_ai",
    )
    for model in (
        User,
        Unit,
        UnitConversion,
        Ingredient,
        Supplier,
        SupplierIngredient,
        PurchaseOrder,
        PurchaseOrderItem,
        GoodsReceipt,
        GoodsReceiptItem,
        StockLot,
        StockMovement,
        Stocktake,
        StocktakeItem,
        DiningTable,
        MenuCategory,
        Dish,
        RecipeVersion,
        RecipeItem,
        Order,
        OrderItem,
    ):
        table = model.__table__.to_metadata(metadata)
        for column in table.primary_key:
            if isinstance(column.type, BigInteger):
                column.type = Integer()
    mappings = metadata.tables["restaurant_ai.supplier_ingredients"]
    Index(
        "uq_supplier_ingredients_one_preferred",
        mappings.c.ingredient_id,
        unique=True,
        sqlite_where=mappings.c.is_preferred.is_(True) & mappings.c.is_active.is_(True),
    )
    recipes = metadata.tables["restaurant_ai.recipe_versions"]
    Index(
        "uq_recipe_versions_one_active_per_dish",
        recipes.c.dish_id,
        unique=True,
        sqlite_where=recipes.c.status == "ACTIVE",
    )
    add_rbac_tables(metadata)
    return metadata


@pytest.fixture
def stock_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        execution_options={"schema_translate_map": {"restaurant_ai": None}},
    )
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    workflow_metadata().create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def stock_session(stock_engine):
    with Session(stock_engine, autoflush=False) as session:
        session.add(
            User(
                user_id=1,
                username="stock_demo",
                password_hash="unused-offline",
                full_name="Offline Stock User",
                status="ACTIVE",
            )
        )
        session.add_all(
            Unit(unit_id=i, unit_code=code, unit_name=code, dimension=dimension)
            for i, code, dimension in ((1, "G", "MASS"), (2, "KG", "MASS"), (3, "BOX", "COUNT"))
        )
        session.add(Supplier(supplier_id=1, supplier_code="LOCAL", supplier_name="Local supplier"))
        session.flush()
        session.add_all(
            Ingredient(
                ingredient_id=i,
                ingredient_code=code,
                ingredient_name=code,
                base_unit_id=1,
                status="ACTIVE",
            )
            for i, code in ((1, "FLOUR"), (2, "CHEESE"))
        )
        session.add(UnitConversion(from_unit_id=2, to_unit_id=1, factor=Decimal("1000")))
        session.flush()
        session.add_all(
            SupplierIngredient(
                supplier_ingredient_id=i,
                supplier_id=1,
                ingredient_id=i,
                purchase_unit_id=2,
                base_qty_per_purchase_unit=Decimal("1000"),
                minimum_order_qty=Decimal("1"),
            )
            for i in (1, 2)
        )
        session.commit()
        seed_inventory_users(session)
        yield session


@pytest.fixture
def stock_client(stock_session, monkeypatch):
    settings = Settings(_env_file=None, DATABASE_URL=None, DEBUG=False)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    app = main_module.create_app()
    app.dependency_overrides[get_db] = lambda: stock_session
    with TestClient(app) as client:
        authenticate_client(client)
        yield client
