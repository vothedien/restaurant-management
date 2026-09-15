"""Real offline transactions for receipts, stock provenance and repeat protection."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError

from app.db.models.inventory import (
    GoodsReceipt,
    StockLot,
    StockMovement,
    SupplierIngredient,
)
from app.modules.purchasing import receipt_service as service_module
from app.modules.purchasing.receipt_repository import GoodsReceiptRepository
from tests.test_purchase_orders import ORDERS, create_order, order_stock

RECEIPTS = "/api/v1/purchasing/goods-receipts"


def ordered_order(client, **changes):
    order = create_order(client, **changes)
    return order_stock(client, order["purchase_order_id"])


def receipt_payload(order, *, quantity="1", **changes):
    return {
        "purchase_order_id": order["purchase_order_id"],
        "received_by": 1,
        "receipt_date": "2026-09-05",
        "items": [
            {
                "purchase_order_item_id": order["items"][0]["purchase_order_item_id"],
                "received_quantity": quantity,
                "actual_unit_price": "42000.50",
            }
        ],
    } | changes


def create_receipt(client, order, **changes):
    response = client.post(RECEIPTS, json=receipt_payload(order, **changes))
    assert response.status_code == 201, response.text
    return response.json()["data"]


def confirm_receipt(client, receipt):
    response = client.post(f"{RECEIPTS}/{receipt['goods_receipt_id']}/confirm")
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_draft_does_not_touch_stock_and_partial_receipts_aggregate(stock_client, stock_session):
    order = ordered_order(stock_client)
    first = create_receipt(stock_client, order)
    assert first["status"] == "DRAFT"
    assert first["items"][0]["lot_code"]
    assert Decimal(first["items"][0]["base_quantity"]) == Decimal("1000")
    assert stock_session.scalar(select(func.count()).select_from(StockLot)) == 0
    confirm_receipt(stock_client, first)
    partial = stock_client.get(f"{ORDERS}/{order['purchase_order_id']}").json()["data"]
    assert partial["status"] == "PARTIALLY_RECEIVED"
    assert Decimal(partial["items"][0]["received_quantity"]) == Decimal("1")
    assert Decimal(partial["items"][0]["remaining_quantity"]) == Decimal("1.5")
    second = create_receipt(stock_client, order, quantity="1.5")
    confirm_receipt(stock_client, second)
    completed = stock_client.get(f"{ORDERS}/{order['purchase_order_id']}").json()["data"]
    assert completed["status"] == "RECEIVED"
    assert Decimal(completed["items"][0]["received_quantity"]) == Decimal("2.5")
    lots = list(stock_session.scalars(select(StockLot).order_by(StockLot.stock_lot_id)))
    assert len(lots) == 2
    assert sum(lot.current_quantity for lot in lots) == Decimal("2500")
    assert lots[0].unit_cost == Decimal("42.0005")
    movements = list(stock_session.scalars(select(StockMovement)))
    assert len(movements) == 2
    assert {m.goods_receipt_item_id for m in movements} == {
        first["items"][0]["goods_receipt_item_id"],
        second["items"][0]["goods_receipt_item_id"],
    }
    assert all(m.movement_type == "RECEIPT" and m.direction == "IN" for m in movements)


def test_confirm_is_repeat_safe_and_cannot_cancel_or_edit_received_order(
    stock_client, stock_session
):
    order = ordered_order(stock_client)
    receipt = create_receipt(stock_client, order, quantity="2.5")
    first = confirm_receipt(stock_client, receipt)
    assert confirm_receipt(stock_client, receipt) == first
    assert stock_session.scalar(select(func.count()).select_from(StockLot)) == 1
    assert stock_session.scalar(select(func.count()).select_from(StockMovement)) == 1
    assert stock_session.scalar(select(StockLot.current_quantity)) == Decimal("2500")
    assert stock_client.post(f"{RECEIPTS}/{receipt['goods_receipt_id']}/cancel").status_code == 409
    assert (
        stock_client.post(
            f"{ORDERS}/{order['purchase_order_id']}/status",
            json={
                "status": "CANCELLED",
                "actor_id": 1,
                "cancellation_reason": "Too late",
            },
        ).status_code
        == 409
    )
    assert (
        stock_client.patch(
            f"{ORDERS}/{order['purchase_order_id']}",
            json={
                "notes": "Cannot edit received order",
            },
        ).status_code
        == 409
    )


def test_drafts_do_not_reserve_stock_and_confirm_rechecks_remaining(stock_client, stock_session):
    order = ordered_order(stock_client)
    first = create_receipt(stock_client, order, quantity="2")
    second = create_receipt(stock_client, order, quantity="2")
    confirm_receipt(stock_client, first)
    response = stock_client.post(f"{RECEIPTS}/{second['goods_receipt_id']}/confirm")
    assert response.status_code == 409
    assert "remaining quantity" in response.text
    assert stock_session.get(GoodsReceipt, second["goods_receipt_id"]).status == "DRAFT"
    assert stock_session.scalar(select(func.sum(StockLot.current_quantity))) == Decimal("2000")
    assert stock_session.scalar(select(func.count()).select_from(StockMovement)) == 1
    assert (
        stock_client.post(RECEIPTS, json=receipt_payload(order, quantity="0.501")).status_code
        == 409
    )


def test_one_order_line_can_be_split_into_distinct_lots(stock_client, stock_session):
    order = ordered_order(stock_client)
    item_id = order["items"][0]["purchase_order_item_id"]
    receipt = create_receipt(
        stock_client,
        order,
        items=[
            {
                "purchase_order_item_id": item_id,
                "received_quantity": "1",
                "actual_unit_price": "10",
                "lot_code": "FLOUR-A",
                "manufacture_date": "2026-09-01",
                "expiry_date": "2030-01-01",
            },
            {
                "purchase_order_item_id": item_id,
                "received_quantity": "1.5",
                "actual_unit_price": "12",
                "lot_code": "FLOUR-B",
            },
        ],
    )
    confirm_receipt(stock_client, receipt)
    lots = list(stock_session.scalars(select(StockLot).order_by(StockLot.lot_code)))
    assert [lot.lot_code for lot in lots] == ["FLOUR-A", "FLOUR-B"]
    assert [lot.unit_cost for lot in lots] == [Decimal("0.0100"), Decimal("0.0120")]
    assert lots[0].expiry_date == date(2030, 1, 1)
    assert (
        stock_client.get(f"{ORDERS}/{order['purchase_order_id']}").json()["data"]["status"]
        == "RECEIVED"
    )


def test_duplicate_lot_conflicts_without_merging_or_partial_writes(stock_client, stock_session):
    order = ordered_order(stock_client)
    item_id = order["items"][0]["purchase_order_item_id"]
    first = create_receipt(
        stock_client,
        order,
        items=[
            {
                "purchase_order_item_id": item_id,
                "received_quantity": "1",
                "actual_unit_price": "10",
                "lot_code": "EXISTING",
            }
        ],
    )
    confirm_receipt(stock_client, first)
    second = create_receipt(
        stock_client,
        order,
        items=[
            {
                "purchase_order_item_id": item_id,
                "received_quantity": "0.5",
                "actual_unit_price": "10",
                "lot_code": "NEW",
            },
            {
                "purchase_order_item_id": item_id,
                "received_quantity": "0.5",
                "actual_unit_price": "10",
                "lot_code": "EXISTING",
            },
        ],
    )
    assert stock_client.post(f"{RECEIPTS}/{second['goods_receipt_id']}/confirm").status_code == 409
    assert stock_session.scalar(select(func.count()).select_from(StockLot)) == 1
    assert stock_session.scalar(select(StockLot.current_quantity)) == Decimal("1000")
    assert stock_session.scalar(select(func.count()).select_from(StockMovement)) == 1
    assert stock_session.get(GoodsReceipt, second["goods_receipt_id"]).status == "DRAFT"


def test_receipt_confirmation_rolls_back_lots_movements_and_status_on_failure(
    stock_client,
    stock_session,
    monkeypatch,
):
    order = ordered_order(
        stock_client,
        items=[
            {"supplier_ingredient_id": i, "ordered_quantity": "1", "expected_unit_price": "10"}
            for i in (1, 2)
        ],
    )
    receipt = create_receipt(
        stock_client,
        order,
        items=[
            {
                "purchase_order_item_id": item["purchase_order_item_id"],
                "received_quantity": "1",
                "actual_unit_price": "11",
            }
            for item in order["items"]
        ],
    )
    calls = 0
    original = service_module.add_movement

    def fail_on_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OperationalError("offline insert", {}, Exception("private driver text"))
        return original(*args, **kwargs)

    monkeypatch.setattr(service_module, "add_movement", fail_on_second)
    response = stock_client.post(f"{RECEIPTS}/{receipt['goods_receipt_id']}/confirm")
    assert response.status_code == 503
    assert "private driver text" not in response.text
    assert stock_session.scalar(select(func.count()).select_from(StockLot)) == 0
    assert stock_session.scalar(select(func.count()).select_from(StockMovement)) == 0
    assert stock_session.get(GoodsReceipt, receipt["goods_receipt_id"]).status == "DRAFT"
    assert (
        stock_client.get(f"{ORDERS}/{order['purchase_order_id']}").json()["data"]["status"]
        == "ORDERED"
    )
    monkeypatch.setattr(service_module, "add_movement", original)
    confirm_receipt(stock_client, receipt)
    assert stock_session.scalar(select(func.count()).select_from(StockMovement)) == 2


def test_receipt_uses_order_conversion_snapshot_after_supplier_update(stock_client, stock_session):
    order = ordered_order(stock_client)
    mapping = stock_session.get(SupplierIngredient, 1)
    mapping.purchase_unit_id = 3
    mapping.base_qty_per_purchase_unit = Decimal("750")
    stock_session.commit()
    receipt = create_receipt(stock_client, order, quantity="1.125")
    assert receipt["items"][0]["purchase_unit_id"] == 2
    assert Decimal(receipt["items"][0]["base_quantity"]) == Decimal("1125")
    confirm_receipt(stock_client, receipt)
    assert stock_session.scalar(select(StockLot.current_quantity)) == Decimal("1125")
    assert stock_session.scalar(select(StockLot.unit_cost)) == Decimal("42.0005")


def test_cancelled_drafts_and_order_preconditions(stock_client, stock_session):
    draft_order = create_order(stock_client)
    assert stock_client.post(RECEIPTS, json=receipt_payload(draft_order)).status_code == 409
    order = order_stock(stock_client, draft_order["purchase_order_id"])
    receipt = create_receipt(stock_client, order)
    cancel = stock_client.post(f"{RECEIPTS}/{receipt['goods_receipt_id']}/cancel")
    assert cancel.status_code == 200
    assert stock_client.post(f"{RECEIPTS}/{receipt['goods_receipt_id']}/cancel").status_code == 200
    assert stock_client.post(f"{RECEIPTS}/{receipt['goods_receipt_id']}/confirm").status_code == 409
    replacement = create_receipt(stock_client, order, quantity="2.5")
    assert (
        stock_client.post(
            f"{ORDERS}/{order['purchase_order_id']}/status",
            json={
                "status": "CANCELLED",
                "actor_id": 1,
                "cancellation_reason": "Cancelled before delivery",
            },
        ).status_code
        == 200
    )
    assert (
        stock_client.post(f"{RECEIPTS}/{replacement['goods_receipt_id']}/confirm").status_code
        == 409
    )
    assert stock_session.scalar(select(func.count()).select_from(StockLot)) == 0


def test_wrong_po_item_and_duplicate_lot_in_draft_rejected(stock_client):
    first = ordered_order(stock_client)
    second = ordered_order(stock_client)
    item = receipt_payload(second)["items"][0]
    assert stock_client.post(RECEIPTS, json=receipt_payload(first, items=[item])).status_code == 400
    item = receipt_payload(first)["items"][0] | {"lot_code": "SAME"}
    assert (
        stock_client.post(RECEIPTS, json=receipt_payload(first, items=[item, item])).status_code
        == 400
    )


@pytest.mark.parametrize(
    "line_changes, expected",
    [
        ({"received_quantity": "0"}, 422),
        ({"received_quantity": "0.0001"}, 422),
        ({"actual_unit_price": "-1"}, 422),
        ({"expiry_date": "2026-09-04"}, 400),
        ({"manufacture_date": "2026-09-06"}, 400),
        ({"manufacture_date": "2026-09-04", "expiry_date": "2026-09-03"}, 422),
        ({"base_quantity": "2"}, 422),
    ],
)
def test_receipt_input_validation(stock_client, line_changes, expected):
    order = ordered_order(stock_client)
    payload = receipt_payload(order)
    payload["items"][0].update(line_changes)
    assert stock_client.post(RECEIPTS, json=payload).status_code == expected


def test_list_filters_detail_and_receipt_dates(stock_client):
    order = ordered_order(stock_client)
    first = create_receipt(stock_client, order, receipt_number="GR-FIRST")
    create_receipt(stock_client, order, receipt_number="GR-SECOND", receipt_date="2026-09-06")
    confirm_receipt(stock_client, first)
    data = stock_client.get(
        RECEIPTS,
        params={
            "purchase_order_id": order["purchase_order_id"],
            "status": "DRAFT",
            "limit": 1,
            "date_from": "2026-09-06",
            "date_to": "2026-09-06",
        },
    ).json()["data"]
    assert data["total"] == 1 and data["items"][0]["receipt_number"] == "GR-SECOND"
    assert stock_client.get(f"{RECEIPTS}/{first['goods_receipt_id']}").status_code == 200
    assert stock_client.get(f"{RECEIPTS}/9999").status_code == 404
    assert stock_client.post(f"{RECEIPTS}/9999/confirm").status_code == 404
    assert (
        stock_client.get(
            RECEIPTS,
            params={
                "date_from": "2026-09-06",
                "date_to": "2026-09-05",
            },
        ).status_code
        == 400
    )
    assert (
        stock_client.post(
            RECEIPTS,
            json=receipt_payload(
                order,
                receipt_date="2026-08-31",
            ),
        ).status_code
        == 400
    )


def test_historical_receipt_marks_now_expired_lot(stock_client, stock_session):
    today = date.today()
    order = ordered_order(
        stock_client,
        order_date=(today - timedelta(days=10)).isoformat(),
        expected_delivery_date=None,
    )
    item = receipt_payload(order)["items"][0] | {
        "expiry_date": (today - timedelta(days=1)).isoformat(),
    }
    receipt = create_receipt(
        stock_client, order, receipt_date=(today - timedelta(days=2)).isoformat(), items=[item]
    )
    confirm_receipt(stock_client, receipt)
    assert stock_session.scalar(select(StockLot.status)) == "EXPIRED"


def test_future_receipts_are_rejected_before_posting(stock_client, stock_session):
    order = ordered_order(stock_client)
    response = stock_client.post(
        RECEIPTS,
        json=receipt_payload(
            order,
            receipt_date=(date.today() + timedelta(days=1)).isoformat(),
        ),
    )
    assert response.status_code == 400
    assert "future" in response.text
    assert stock_session.scalar(select(func.count()).select_from(GoodsReceipt)) == 0
    assert stock_session.scalar(select(func.count()).select_from(StockLot)) == 0


def test_postgres_receipt_lock_refresh_and_parent_lock_order(stock_client, stock_session):
    class Capture:
        def scalar(self, statement):
            self.statement = statement

    capture = Capture()
    GoodsReceiptRepository.get(capture, 1, lock=True)
    assert "FOR UPDATE" in str(capture.statement.compile(dialect=postgresql.dialect()))
    assert capture.statement.get_execution_options()["populate_existing"] is True

    order = ordered_order(stock_client)
    receipt = create_receipt(stock_client, order)
    locked_tables = []

    def capture_locks(state):
        statement = state.statement
        if getattr(statement, "_for_update_arg", None) is not None:
            locked_tables.extend(table.name for table in statement.get_final_froms())

    event.listen(stock_session, "do_orm_execute", capture_locks)
    try:
        confirm_receipt(stock_client, receipt)
    finally:
        event.remove(stock_session, "do_orm_execute", capture_locks)
    assert locked_tables[:2] == ["purchase_orders", "goods_receipts"]
    assert locked_tables.index("ingredients") < locked_tables.index("stock_lots")
