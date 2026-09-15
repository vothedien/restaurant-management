"""Offline consumption tests; no kitchen endpoint or live DB is fabricated."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, event, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError, BusinessRuleError, ConflictError, NotFoundError
from app.db.models.catalog import (
    DiningTable,
    Dish,
    MenuCategory,
    RecipeItem,
    RecipeVersion,
    UnitConversion,
)
from app.db.models.inventory import StockLot, StockMovement
from app.db.models.sales import Order, OrderItem
from app.modules.inventory.consumption_service import ConsumptionService


@pytest.fixture
def consumption_data(stock_session: Session) -> None:
    """Two dishes use one pinned recipe and need stock spanning two flour lots."""
    now = datetime.now(UTC)
    stock_session.add_all(
        [
            MenuCategory(category_id=101, category_code="FOOD", category_name="Food"),
            DiningTable(table_id=101, table_code="T101", capacity=4),
        ]
    )
    stock_session.flush()
    stock_session.add_all(
        [
            Dish(
                dish_id=101,
                dish_code="PIZZA101",
                dish_name="Pizza",
                category_id=101,
                selling_price=Decimal("100.00"),
            ),
            Order(
                order_id=101,
                order_number="ORDER101",
                table_id=101,
                opened_by=1,
                opened_at=now,
                status="IN_PROGRESS",
            ),
        ]
    )
    stock_session.flush()
    stock_session.add(
        RecipeVersion(
            recipe_version_id=101,
            dish_id=101,
            version_no=1,
            status="ACTIVE",
            effective_from=date.today() - timedelta(days=1),
        )
    )
    stock_session.flush()
    stock_session.add_all(
        [
            RecipeItem(
                recipe_item_id=101,
                recipe_version_id=101,
                ingredient_id=1,
                quantity=Decimal("0.250"),
                unit_id=2,
                base_quantity=Decimal("250.000"),
            ),
            RecipeItem(
                recipe_item_id=102,
                recipe_version_id=101,
                ingredient_id=2,
                quantity=Decimal("2.000"),
                unit_id=1,
                base_quantity=Decimal("2.000"),
            ),
            OrderItem(
                order_item_id=101,
                order_id=101,
                dish_id=101,
                recipe_version_id=101,
                quantity=2,
                unit_price=Decimal("100.00"),
                status="COMPLETED",
                completed_at=now,
            ),
        ]
    )
    for lot_id, ingredient_id, quantity, expiry in (
        (101, 1, "250.000", 10),
        (102, 1, "300.000", 20),
        (103, 2, "5.000", 30),
    ):
        stock_session.add(
            StockLot(
                stock_lot_id=lot_id,
                ingredient_id=ingredient_id,
                lot_code=f"CONSUMPTION-{lot_id}",
                expiry_date=date.today() + timedelta(days=expiry),
                received_quantity=Decimal(quantity),
                current_quantity=Decimal(quantity),
                unit_cost=Decimal("1.0000"),
                status="ACTIVE",
            )
        )
    stock_session.commit()


def snapshot(engine) -> tuple[list[Decimal], int, str]:
    with Session(engine) as session:
        quantities = list(
            session.scalars(
                select(StockLot.current_quantity)
                .where(StockLot.stock_lot_id.in_([101, 102, 103]))
                .order_by(StockLot.stock_lot_id)
            )
        )
        movements = session.scalar(
            select(func.count())
            .select_from(StockMovement)
            .where(StockMovement.order_item_id == 101)
        )
        item_status = session.get(OrderItem, 101).status
    return quantities, movements, item_status


def test_completed_item_consumes_pinned_recipe_in_base_units_and_fefo(
    stock_session, stock_engine, consumption_data
):
    result = ConsumptionService().consume_completed_item(stock_session, 101, performed_by=1)

    assert result.order_item_id == 101
    assert result.recipe_version_id == 101
    assert result.already_consumed is False
    assert {row.ingredient_id: row.base_quantity for row in result.requirements} == {
        1: Decimal("500.000"),
        2: Decimal("4.000"),
    }
    assert [(row.stock_lot_id, row.quantity) for row in result.movements] == [
        (101, Decimal("250.000")),
        (102, Decimal("250.000")),
        (103, Decimal("4.000")),
    ]
    assert all(row.order_item_id == 101 and row.performed_by == 1 for row in result.movements)
    assert snapshot(stock_engine) == (
        [Decimal("0.000"), Decimal("50.000"), Decimal("1.000")],
        3,
        "COMPLETED",
    )
    with Session(stock_engine) as verification:
        assert verification.get(StockLot, 101).status == "DEPLETED"
        movements = list(verification.scalars(select(StockMovement)))
        assert all(
            row.movement_type == "CONSUMPTION" and row.direction == "OUT" for row in movements
        )


def test_retry_does_not_deduct_again_when_remaining_stock_is_insufficient(
    stock_session, stock_engine, consumption_data
):
    service = ConsumptionService()
    first = service.consume_completed_item(stock_session, 101)
    after_first = snapshot(stock_engine)

    second = service.consume_completed_item(stock_session, 101)

    assert second.already_consumed is True
    assert second.movements == first.movements
    assert second.requirements == first.requirements
    assert snapshot(stock_engine) == after_first


def test_consumption_uses_conversion_snapshot_after_conversion_changes(
    stock_session, consumption_data
):
    stock_session.execute(delete(UnitConversion))
    stock_session.add(UnitConversion(from_unit_id=2, to_unit_id=1, factor=Decimal("1.000000")))
    stock_session.commit()

    result = ConsumptionService().consume_completed_item(stock_session, 101)

    assert result.requirements[0].base_quantity == Decimal("500.000")


@pytest.mark.parametrize("recipe_status", ["INACTIVE", "EXPIRED"])
def test_historical_pinned_recipe_remains_usable(stock_session, consumption_data, recipe_status):
    recipe = stock_session.get(RecipeVersion, 101)
    recipe.status = recipe_status
    recipe.effective_from = date.today() - timedelta(days=20)
    recipe.effective_to = date.today() - timedelta(days=10)
    stock_session.commit()

    result = ConsumptionService().consume_completed_item(stock_session, 101)

    assert result.recipe_version_id == 101
    assert result.requirements[0].base_quantity == Decimal("500.000")


def test_new_active_recipe_does_not_replace_the_order_recipe(stock_session, consumption_data):
    stock_session.get(RecipeVersion, 101).status = "INACTIVE"
    stock_session.flush()
    stock_session.add(
        RecipeVersion(
            recipe_version_id=102,
            dish_id=101,
            version_no=2,
            status="ACTIVE",
            effective_from=date.today(),
        )
    )
    stock_session.flush()
    stock_session.add(
        RecipeItem(
            recipe_version_id=102,
            ingredient_id=1,
            quantity=Decimal("900.000"),
            unit_id=1,
            base_quantity=Decimal("900.000"),
        )
    )
    stock_session.commit()

    result = ConsumptionService().consume_completed_item(stock_session, 101)

    assert result.recipe_version_id == 101
    assert result.requirements[0].base_quantity == Decimal("500.000")


@pytest.mark.parametrize("status", ["PENDING", "SENT", "PREPARING", "CANCELLED"])
def test_noncompleted_item_cannot_consume_stock(
    stock_session, stock_engine, consumption_data, status
):
    item = stock_session.get(OrderItem, 101)
    item.status = status
    if status == "CANCELLED":
        item.cancelled_at = datetime.now(UTC)
        item.cancellation_reason = "Customer cancelled"
    stock_session.commit()
    before = snapshot(stock_engine)

    with pytest.raises(ConflictError, match="completed"):
        ConsumptionService().consume_completed_item(stock_session, 101)

    assert snapshot(stock_engine) == before
    assert not stock_session.in_transaction()


def test_completed_status_requires_completion_timestamp(
    stock_session, stock_engine, consumption_data
):
    stock_session.get(OrderItem, 101).completed_at = None
    stock_session.commit()
    before = snapshot(stock_engine)

    with pytest.raises(ConflictError, match="completed_at"):
        ConsumptionService().consume_completed_item(stock_session, 101)

    assert snapshot(stock_engine) == before


def test_missing_pin_is_a_business_error_without_current_recipe_fallback(
    stock_session, stock_engine, consumption_data
):
    stock_session.get(OrderItem, 101).recipe_version_id = None
    stock_session.commit()
    before = snapshot(stock_engine)

    with pytest.raises(BusinessRuleError, match="pinned recipe") as failure:
        ConsumptionService().consume_completed_item(stock_session, 101)

    assert failure.value.status_code == 400
    assert snapshot(stock_engine) == before


def test_pinned_recipe_must_belong_to_the_order_dish(stock_session, stock_engine, consumption_data):
    stock_session.add(
        Dish(
            dish_id=102,
            dish_code="OTHER102",
            dish_name="Other dish",
            category_id=101,
            selling_price=Decimal("10.00"),
        )
    )
    stock_session.flush()
    stock_session.get(OrderItem, 101).dish_id = 102
    stock_session.commit()
    before = snapshot(stock_engine)

    with pytest.raises(BusinessRuleError, match="does not belong"):
        ConsumptionService().consume_completed_item(stock_session, 101)

    assert snapshot(stock_engine) == before


@pytest.mark.parametrize("invalid_recipe", ["DRAFT", "empty"])
def test_draft_or_empty_recipe_cannot_consume_stock(
    stock_session, stock_engine, consumption_data, invalid_recipe
):
    if invalid_recipe == "DRAFT":
        stock_session.get(RecipeVersion, 101).status = "DRAFT"
    else:
        stock_session.execute(delete(RecipeItem).where(RecipeItem.recipe_version_id == 101))
    stock_session.commit()
    before = snapshot(stock_engine)

    with pytest.raises(BusinessRuleError):
        ConsumptionService().consume_completed_item(stock_session, 101)

    assert snapshot(stock_engine) == before


def test_missing_order_item_is_not_found(stock_session):
    with pytest.raises(NotFoundError, match="Order item"):
        ConsumptionService().consume_completed_item(stock_session, 999)


def test_shortage_of_one_ingredient_rolls_back_every_ingredient(
    stock_session, stock_engine, consumption_data
):
    stock_session.get(StockLot, 103).current_quantity = Decimal("3.999")
    stock_session.commit()
    before = snapshot(stock_engine)

    with pytest.raises(ApplicationError):
        ConsumptionService().consume_completed_item(stock_session, 101)

    assert snapshot(stock_engine) == before
    assert not stock_session.in_transaction()


def test_decimal_recipe_multiplication_is_exact(stock_session, consumption_data):
    stock_session.get(RecipeItem, 101).base_quantity = Decimal("0.333")
    stock_session.get(RecipeItem, 102).base_quantity = Decimal("0.001")
    stock_session.get(OrderItem, 101).quantity = 3
    stock_session.commit()

    result = ConsumptionService().consume_completed_item(stock_session, 101)

    assert [row.base_quantity for row in result.requirements] == [
        Decimal("0.999"),
        Decimal("0.003"),
    ]


def test_overflow_cannot_create_partial_consumption(stock_session, stock_engine, consumption_data):
    stock_session.get(OrderItem, 101).quantity = 2_147_483_647
    stock_session.commit()
    before = snapshot(stock_engine)

    with pytest.raises(BusinessRuleError, match="supported range"):
        ConsumptionService().consume_completed_item(stock_session, 101)

    assert snapshot(stock_engine) == before


def test_in_transaction_consumption_never_commits_completion(
    stock_session, stock_engine, consumption_data
):
    item = stock_session.get(OrderItem, 101)
    item.status = "PREPARING"
    item.completed_at = None
    stock_session.commit()
    before = snapshot(stock_engine)
    item.status = "COMPLETED"
    item.completed_at = datetime.now(UTC)

    result = ConsumptionService().consume_in_transaction(stock_session, 101)

    assert result.already_consumed is False
    assert stock_session.in_transaction()
    stock_session.rollback()
    assert snapshot(stock_engine) == before


def test_failed_inventory_write_rolls_back_completion_and_stock(
    stock_session, stock_engine, consumption_data, monkeypatch
):
    item = stock_session.get(OrderItem, 101)
    item.status = "PREPARING"
    item.completed_at = None
    stock_session.commit()
    before = snapshot(stock_engine)
    service = ConsumptionService()
    consume = service.stock_service.consume

    def fail_after_stock_write(*args, **kwargs):
        consume(*args, **kwargs)
        stock_session.flush()
        raise IntegrityError("private SQL", {}, Exception("private driver details"))

    monkeypatch.setattr(service.stock_service, "consume", fail_after_stock_write)
    item.status = "COMPLETED"
    item.completed_at = datetime.now(UTC)

    with pytest.raises(ConflictError) as failure:
        service.consume_completed_item(stock_session, 101)

    assert "private" not in str(failure.value)
    assert snapshot(stock_engine) == before


def test_postgresql_source_lock_refreshes_before_idempotency_check(stock_session, consumption_data):
    statements = []

    def record_statement(state):
        if state.is_select:
            statements.append(
                (
                    str(state.statement.compile(dialect=postgresql.dialect())),
                    state.execution_options.get("populate_existing", False),
                )
            )

    event.listen(stock_session, "do_orm_execute", record_statement)
    try:
        ConsumptionService().consume_completed_item(stock_session, 101)
    finally:
        event.remove(stock_session, "do_orm_execute", record_statement)

    source_index = next(
        index
        for index, (sql, _) in enumerate(statements)
        if "FROM restaurant_ai.order_items" in sql
    )
    movement_index = next(
        index
        for index, (sql, _) in enumerate(statements)
        if "FROM restaurant_ai.stock_movements" in sql
    )
    assert "FOR UPDATE" in statements[source_index][0]
    assert statements[source_index][1] is True
    assert source_index < movement_index


def test_cached_completed_item_is_refreshed_before_stock_changes(
    stock_session, stock_engine, consumption_data
):
    cached_item = stock_session.get(OrderItem, 101)
    assert cached_item.status == "COMPLETED"
    with Session(stock_engine) as other_session:
        other_session.get(OrderItem, 101).status = "PREPARING"
        other_session.commit()
    assert cached_item.status == "COMPLETED"
    before = snapshot(stock_engine)

    with pytest.raises(ConflictError, match="completed"):
        ConsumptionService().consume_completed_item(stock_session, 101)

    assert snapshot(stock_engine) == before
