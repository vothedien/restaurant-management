from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.catalog import Ingredient, UnitConversion
from app.db.models.inventory import StockLot, StockMovement

PREFIX = "/api/v1/inventory"


def seed_lot(
    session,
    lot_id=1,
    *,
    quantity="100",
    current=None,
    status="ACTIVE",
    expiry=None,
    ingredient_id=1,
):
    lot = StockLot(
        stock_lot_id=lot_id,
        ingredient_id=ingredient_id,
        lot_code=f"LOT-{lot_id}",
        received_quantity=Decimal(quantity),
        current_quantity=Decimal(current if current is not None else quantity),
        unit_cost=Decimal("1.2500"),
        status=status,
        expiry_date=expiry,
    )
    session.add(lot)
    session.commit()
    return lot


def issue(client, **changes):
    return client.post(
        f"{PREFIX}/stock/issues",
        json={
            "ingredient_id": 1,
            "quantity": "20",
            "unit_id": 1,
            "performed_by": 1,
            "reason": "Kitchen test issue",
            **changes,
        },
    )


def test_balances_reconcile_all_lots_but_separate_unavailable(stock_session, stock_client):
    seed_lot(stock_session, 1)
    seed_lot(stock_session, 2, quantity="40", status="BLOCKED")
    seed_lot(stock_session, 3, quantity="30", expiry=date.today() - timedelta(days=1))
    seed_lot(stock_session, 4, quantity="20", current="0", status="DEPLETED")
    result = stock_client.get(f"{PREFIX}/stock").json()["data"]
    first, empty = result["items"]
    assert Decimal(first["current_quantity"]) == 170
    assert Decimal(first["available_quantity"]) == 100
    assert Decimal(first["unavailable_quantity"]) == 70
    assert Decimal(empty["current_quantity"]) == 0
    lots = stock_client.get(f"{PREFIX}/stock-lots?ingredient_id=1").json()["data"]
    assert sum(Decimal(lot["current_quantity"]) for lot in lots["items"]) == 170
    available = stock_client.get(f"{PREFIX}/stock-lots?available_only=true").json()["data"]
    assert available["total"] == 1


def test_issue_converts_decimal_and_allocates_fefo(stock_session, stock_client):
    seed_lot(stock_session, 1, expiry=None)
    seed_lot(stock_session, 2, quantity="75", expiry=date.today() + timedelta(days=2))
    seed_lot(stock_session, 3, quantity="25", expiry=date.today())
    result = issue(stock_client, quantity="0.125", unit_id=2)
    assert result.status_code == 201, result.text
    moves = result.json()["data"]["movements"]
    assert [(m["stock_lot_id"], Decimal(m["quantity"])) for m in moves] == [
        (3, Decimal("25")),
        (2, Decimal("75")),
        (1, Decimal("25")),
    ]
    assert all(m["movement_type"] == "ADJUSTMENT" and m["direction"] == "OUT" for m in moves)
    assert stock_session.get(StockLot, 3).status == "DEPLETED"
    balance = stock_client.get(f"{PREFIX}/stock?ingredient_id=1").json()["data"]["items"][0]
    assert Decimal(balance["current_quantity"]) == 75


def test_insufficient_eligible_stock_rolls_back(stock_session, stock_client, stock_engine):
    seed_lot(stock_session, 1, quantity="5")
    seed_lot(stock_session, 2, quantity="500", status="BLOCKED")
    response = issue(stock_client, quantity="6")
    assert response.status_code == 409
    assert not stock_session.in_transaction()
    with Session(stock_engine) as verification:
        assert verification.get(StockLot, 1).current_quantity == 5
        assert verification.scalar(select(func.count()).select_from(StockMovement)) == 0


@pytest.mark.parametrize("quantity", ["-1", "0", "NaN", "Infinity", "0.0001", "100000000000"])
def test_invalid_issue_quantities(stock_client, quantity):
    assert issue(stock_client, quantity=quantity).status_code == 422


def test_rejects_missing_incompatible_or_inexact_conversion(stock_session, stock_client):
    seed_lot(stock_session)
    assert issue(stock_client, unit_id=999).status_code == 404
    assert issue(stock_client, unit_id=3).status_code == 400
    conversion = stock_session.scalar(select(UnitConversion))
    conversion.factor = Decimal("0.333333")
    stock_session.commit()
    assert issue(stock_client, quantity="0.001", unit_id=2).status_code == 400
    assert stock_session.get(StockLot, 1).current_quantity == 100


def test_adjust_target_is_repeat_safe_and_cannot_exceed_original_receipt(
    stock_session, stock_client
):
    seed_lot(stock_session, current="50")
    payload = {"actual_quantity": "75.125", "performed_by": 1, "reason": "Recount"}
    response = stock_client.post(f"{PREFIX}/stock-lots/1/adjust", json=payload)
    assert response.status_code == 200, response.text
    movement = response.json()["data"]["movements"][0]
    assert movement["direction"] == "IN" and Decimal(movement["quantity"]) == Decimal("25.125")
    retry = stock_client.post(f"{PREFIX}/stock-lots/1/adjust", json=payload)
    assert retry.json()["data"]["movements"] == []
    payload["actual_quantity"] = "101"
    assert stock_client.post(f"{PREFIX}/stock-lots/1/adjust", json=payload).status_code == 409
    assert stock_session.get(StockLot, 1).received_quantity == 100


def test_adjust_does_not_unblock_lots_and_allows_count_inactive_ingredient(
    stock_session, stock_client
):
    seed_lot(stock_session, status="BLOCKED")
    stock_session.get(Ingredient, 1).status = "INACTIVE"
    stock_session.commit()
    response = stock_client.post(
        f"{PREFIX}/stock-lots/1/adjust",
        json={"actual_quantity": "0", "performed_by": 1, "reason": "Discard blocked stock"},
    )
    assert response.status_code == 200, response.text
    assert stock_session.get(StockLot, 1).status == "BLOCKED"


def test_history_filters_time_order_and_pagination(stock_session, stock_client):
    seed_lot(stock_session)
    first = issue(stock_client).json()["data"]["movements"][0]
    assert issue(stock_client, quantity="10").status_code == 201
    data = stock_client.get(
        f"{PREFIX}/stock-movements",
        params={
            "ingredient_id": 1,
            "stock_lot_id": 1,
            "movement_type": "ADJUSTMENT",
            "limit": 1,
            "occurred_from": "2000-01-01T00:00:00Z",
            "occurred_to": "2100-01-01T00:00:00Z",
            "offset": 1,
        },
    ).json()["data"]
    assert data["total"] == 2
    assert data["items"][0]["stock_movement_id"] == first["stock_movement_id"]
    assert (
        stock_client.get(
            f"{PREFIX}/stock-movements",
            params={
                "occurred_from": "2100-01-01T00:00:00Z",
                "occurred_to": "2000-01-01T00:00:00Z",
            },
        ).status_code
        == 400
    )
    assert stock_client.get(f"{PREFIX}/stock-movements?occurred_from=2020-01-01").status_code == 422


def test_issue_commit_failure_restores_lot_and_history(stock_session, stock_client, monkeypatch):
    seed_lot(stock_session)
    with monkeypatch.context() as patch:

        def fail():
            raise IntegrityError("private statement", {}, Exception("private detail"))

        patch.setattr(stock_session, "commit", fail)
        response = issue(stock_client)
    assert response.status_code == 409 and "private" not in response.text
    assert not stock_session.in_transaction()
    assert stock_session.get(StockLot, 1).current_quantity == 100
    assert stock_session.scalar(select(func.count()).select_from(StockMovement)) == 0


def test_issue_postgresql_lock_order(stock_session, stock_client):
    seed_lot(stock_session)
    locks = []

    def capture(state):
        if getattr(state.statement, "_for_update_arg", None) is not None:
            locks.append(str(state.statement.compile(dialect=postgresql.dialect())))

    event.listen(stock_session, "do_orm_execute", capture)
    try:
        assert issue(stock_client).status_code == 201
    finally:
        event.remove(stock_session, "do_orm_execute", capture)
    assert "FROM restaurant_ai.ingredients" in locks[0]
    assert "ORDER BY restaurant_ai.stock_lots.stock_lot_id FOR UPDATE" in locks[-1]


def test_existing_quantity_references_freeze_ingredient_base_unit(stock_session, stock_client):
    response = stock_client.patch(f"{PREFIX}/ingredients/1", json={"base_unit_id": 2})
    assert response.status_code == 409, response.text
    assert stock_session.get(Ingredient, 1).base_unit_id == 1
    response = stock_client.patch(f"{PREFIX}/ingredients/1", json={"ingredient_name": "New flour"})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["ingredient_name"] == "New flour"


def test_unused_ingredient_base_unit_can_be_corrected(stock_session, stock_client):
    stock_session.add(
        Ingredient(
            ingredient_id=9, ingredient_code="UNUSED", ingredient_name="Unused", base_unit_id=1
        )
    )
    stock_session.commit()
    response = stock_client.patch(f"{PREFIX}/ingredients/9", json={"base_unit_id": 2})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["base_unit"]["unit_id"] == 2


def test_unit_dimension_is_immutable(stock_client):
    assert stock_client.patch(f"{PREFIX}/units/1", json={"dimension": "COUNT"}).status_code == 409


def test_inactive_ingredient_stock_is_visible_but_unavailable(stock_session, stock_client):
    seed_lot(stock_session)
    stock_session.get(Ingredient, 1).status = "INACTIVE"
    stock_session.commit()
    data = stock_client.get(f"{PREFIX}/stock?ingredient_id=1").json()["data"]["items"][0]
    assert Decimal(data["current_quantity"]) == 100
    assert Decimal(data["available_quantity"]) == 0
    assert stock_client.get(f"{PREFIX}/stock-lots?available_only=true").json()["data"]["total"] == 0
    assert issue(stock_client).status_code == 400
