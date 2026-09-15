"""Executable offline handoff: A -> B -> C -> E service -> D.

Sales has no completion API yet. Its order item is created only as a local test
fixture, then the inventory integration service runs in the caller transaction.
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.db.models.catalog import DiningTable, Dish, MenuCategory
from app.db.models.inventory import StockMovement
from app.db.models.sales import Order, OrderItem
from app.modules.inventory.consumption_service import ConsumptionService
from app.modules.inventory.stock_common import stock_now, transaction


def test_purchase_receipt_consumption_stocktake_demo(stock_client, stock_session):
    client, session = stock_client, stock_session

    def request(method, path, data=None, expected=200):
        result = client.request(method, f"/api/v1/{path}", json=data)
        assert result.status_code == expected, result.text
        return result.json()["data"]

    def balance():
        return {
            row["ingredient_id"]: Decimal(row["current_quantity"])
            for row in request("GET", "inventory/stock")["items"]
        }

    # The only catalog/sales inserts in this demo are isolated fixture data.
    session.add(MenuCategory(category_id=1, category_code="PIZZA", category_name="Pizza"))
    session.add(DiningTable(table_id=1, table_code="DEMO-1", capacity=4))
    session.flush()
    session.add(
        Dish(
            dish_id=1,
            dish_code="DEMO-PIZZA",
            dish_name="Offline pizza",
            category_id=1,
            selling_price=Decimal("1"),
        )
    )
    session.commit()
    recipe = request("POST", "recipes", {"dish_id": 1}, expected=201)
    recipe_id = recipe["recipe_version_id"]
    recipe = request(
        "PUT",
        f"recipes/{recipe_id}/items",
        {
            "items": [
                {"ingredient_id": 1, "unit_id": 2, "quantity": "0.250"},
                {"ingredient_id": 2, "unit_id": 1, "quantity": "2"},
            ]
        },
    )
    assert Decimal(recipe["items"][0]["base_quantity"]) == 250
    request("POST", f"recipes/{recipe_id}/activate")

    order = request(
        "POST",
        "purchasing/purchase-orders",
        {
            "supplier_id": 1,
            "created_by": 1,
            "items": [
                {"supplier_ingredient_id": 1, "ordered_quantity": "2", "expected_unit_price": "20"},
                {"supplier_ingredient_id": 2, "ordered_quantity": "1", "expected_unit_price": "40"},
            ],
        },
        expected=201,
    )
    purchase_id = order["purchase_order_id"]
    flour_line, cheese_line = [item["purchase_order_item_id"] for item in order["items"]]
    for state in ("PENDING_APPROVAL", "APPROVED", "ORDERED"):
        request(
            "POST",
            f"purchasing/purchase-orders/{purchase_id}/status",
            {"status": state, "actor_id": 1},
        )
    assert balance() == {1: 0, 2: 0}

    expiry = (date.today() + timedelta(days=30)).isoformat()
    receipt = request(
        "POST",
        "purchasing/goods-receipts",
        {
            "purchase_order_id": purchase_id,
            "received_by": 1,
            "items": [
                {
                    "purchase_order_item_id": flour_line,
                    "received_quantity": "1",
                    "actual_unit_price": "21",
                    "lot_code": "FLOUR-FIRST",
                    "expiry_date": expiry,
                },
                {
                    "purchase_order_item_id": cheese_line,
                    "received_quantity": "1",
                    "actual_unit_price": "42",
                    "lot_code": "CHEESE-FIRST",
                    "expiry_date": expiry,
                },
            ],
        },
        expected=201,
    )
    assert balance() == {1: 0, 2: 0}
    receipt_id = receipt["goods_receipt_id"]
    request("POST", f"purchasing/goods-receipts/{receipt_id}/confirm")
    request("POST", f"purchasing/goods-receipts/{receipt_id}/confirm")
    assert balance() == {1: 1000, 2: 1000}
    assert (
        request("GET", f"purchasing/purchase-orders/{purchase_id}")["status"]
        == "PARTIALLY_RECEIVED"
    )
    receipt = request(
        "POST",
        "purchasing/goods-receipts",
        {
            "purchase_order_id": purchase_id,
            "received_by": 1,
            "items": [
                {
                    "purchase_order_item_id": flour_line,
                    "received_quantity": "1",
                    "actual_unit_price": "21",
                    "lot_code": "FLOUR-SECOND",
                    "expiry_date": expiry,
                }
            ],
        },
        expected=201,
    )
    request("POST", f"purchasing/goods-receipts/{receipt['goods_receipt_id']}/confirm")
    assert request("GET", f"purchasing/purchase-orders/{purchase_id}")["status"] == "RECEIVED"
    assert balance() == {1: 2000, 2: 1000}

    # Demonstrate the future Sales transaction boundary without adding a fake API.
    session.add(Order(order_id=1, order_number="OFFLINE-ORDER", table_id=1, opened_by=1))
    session.flush()
    session.add(
        OrderItem(
            order_item_id=1,
            order_id=1,
            dish_id=1,
            recipe_version_id=recipe_id,
            quantity=2,
            unit_price=Decimal("1"),
            status="PREPARING",
        )
    )
    session.commit()
    with transaction(session):
        item = session.get(OrderItem, 1)
        item.status = "COMPLETED"
        item.completed_at = stock_now(session)
        consumed = ConsumptionService().consume_in_transaction(session, 1, performed_by=1)
    assert consumed.already_consumed is False
    assert ConsumptionService().consume_completed_item(session, 1).already_consumed is True
    assert balance() == {1: 1500, 2: 996}

    lots = request("GET", "inventory/stock-lots")["items"]
    flour_lot = next(lot for lot in lots if lot["lot_code"] == "FLOUR-FIRST")
    assert Decimal(flour_lot["current_quantity"]) == 500
    stocktake = request("POST", "inventory/stocktakes", {"created_by": 1}, expected=201)
    stocktake_id = stocktake["stocktake_id"]
    stocktake = request(
        "POST",
        f"inventory/stocktakes/{stocktake_id}/start",
        {"stock_lot_ids": [flour_lot["stock_lot_id"]]},
    )
    item_id = stocktake["items"][0]["stocktake_item_id"]
    counted = request(
        "PATCH",
        f"inventory/stocktakes/{stocktake_id}/items/{item_id}",
        {
            "actual_quantity": "490",
            "adjustment_reason": "Physical count: spilled flour",
        },
    )
    assert Decimal(counted["items"][0]["variance_quantity"]) == -10
    assert balance() == {1: 1500, 2: 996}
    request("POST", f"inventory/stocktakes/{stocktake_id}/complete", {"completed_by": 1})
    request("POST", f"inventory/stocktakes/{stocktake_id}/complete", {"completed_by": 1})
    assert balance() == {1: 1490, 2: 996}

    ledger = {1: Decimal("0"), 2: Decimal("0")}
    for movement in session.scalars(select(StockMovement)):
        ledger[movement.ingredient_id] += movement.quantity * (
            1 if movement.direction == "IN" else -1
        )
    assert ledger == balance()
