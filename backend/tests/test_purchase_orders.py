"""Offline purchase order workflows; no application database connection is used."""

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql

from app.db.models.catalog import Ingredient, Unit
from app.db.models.inventory import PurchaseOrder, StockLot, StockMovement, SupplierIngredient
from app.modules.purchasing.order_repository import PurchaseOrderRepository

ORDERS = "/api/v1/purchasing/purchase-orders"


def order_payload(**changes):
    payload = {
        "supplier_id": 1,
        "created_by": 1,
        "order_date": "2026-09-01",
        "expected_delivery_date": "2026-09-20",
        "items": [
            {
                "supplier_ingredient_id": 1,
                "ordered_quantity": "2.500",
                "expected_unit_price": "35000.25",
            }
        ],
    }
    return payload | changes


def create_order(client, **changes):
    response = client.post(ORDERS, json=order_payload(**changes))
    assert response.status_code == 201, response.text
    return response.json()["data"]


def order_stock(client, order_id):
    for status in ("PENDING_APPROVAL", "APPROVED", "ORDERED"):
        response = client.post(
            f"{ORDERS}/{order_id}/status", json={"status": status, "actor_id": 1}
        )
        assert response.status_code == 200, response.text
    return response.json()["data"]


def test_create_snapshots_decimal_amounts_without_stock(stock_client, stock_session):
    order = create_order(stock_client)
    assert order["status"] == "DRAFT"
    assert Decimal(order["subtotal_amount"]) == Decimal("87500.63")
    item = order["items"][0]
    assert item["purchase_unit_id"] == 2
    assert Decimal(item["ordered_base_qty"]) == Decimal("2500")
    assert Decimal(item["base_qty_per_purchase_unit"]) == Decimal("1000")
    assert Decimal(item["received_quantity"]) == 0
    assert Decimal(item["remaining_quantity"]) == Decimal("2.5")
    order_stock(stock_client, order["purchase_order_id"])
    assert stock_session.scalar(select(func.count()).select_from(StockLot)) == 0
    assert stock_session.scalar(select(func.count()).select_from(StockMovement)) == 0


def test_draft_edit_and_filtered_pagination(stock_client):
    order = create_order(stock_client, purchase_order_number="PO-EDIT")
    order_id = order["purchase_order_id"]
    response = stock_client.patch(
        f"{ORDERS}/{order_id}",
        json={
            "notes": "Ready for approval",
            "items": [
                {
                    "supplier_ingredient_id": 2,
                    "ordered_quantity": "3",
                    "expected_unit_price": "20.50",
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    edited = response.json()["data"]
    assert Decimal(edited["subtotal_amount"]) == Decimal("61.50")
    assert len(edited["items"]) == 1
    assert edited["items"][0]["supplier_ingredient_id"] == 2
    create_order(stock_client)
    listed = stock_client.get(
        ORDERS, params={"supplier_id": 1, "status": "DRAFT", "limit": 1, "offset": 1}
    ).json()["data"]
    assert listed["total"] == 2
    assert listed["items"][0]["purchase_order_number"] == "PO-EDIT"
    assert stock_client.get(f"{ORDERS}/{order_id}").status_code == 200


def test_transitions_and_cancellation(stock_client):
    order_id = create_order(stock_client)["purchase_order_id"]
    assert (
        stock_client.post(
            f"{ORDERS}/{order_id}/status",
            json={
                "status": "APPROVED",
                "actor_id": 1,
            },
        ).status_code
        == 409
    )
    ordered = order_stock(stock_client, order_id)
    assert ordered["status"] == "ORDERED" and ordered["approved_by"] == 1
    assert stock_client.patch(f"{ORDERS}/{order_id}", json={"notes": "No"}).status_code == 409
    cancelled = stock_client.post(
        f"{ORDERS}/{order_id}/status",
        json={
            "status": "CANCELLED",
            "actor_id": 1,
            "cancellation_reason": "Supplier cannot deliver",
        },
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["cancelled_at"] is not None
    assert (
        stock_client.post(
            f"{ORDERS}/{order_id}/status",
            json={
                "status": "ORDERED",
                "actor_id": 1,
            },
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"items": []},
        {
            "items": [
                {"supplier_ingredient_id": 1, "ordered_quantity": "0", "expected_unit_price": "1"}
            ]
        },
        {
            "items": [
                {
                    "supplier_ingredient_id": 1,
                    "ordered_quantity": "1.0001",
                    "expected_unit_price": "1",
                }
            ]
        },
        {"items": [{"supplier_ingredient_id": 1, "ordered_quantity": "1"}]},
        {"expected_delivery_date": "2026-08-01"},
        {"status": "ORDERED"},
    ],
)
def test_invalid_inputs(stock_client, changes):
    assert stock_client.post(ORDERS, json=order_payload(**changes)).status_code == 422


def test_missing_references_minimum_and_duplicate_mapping(stock_client):
    assert stock_client.post(ORDERS, json=order_payload(supplier_id=999)).status_code == 404
    forged = stock_client.post(ORDERS, json=order_payload(created_by=999))
    assert forged.status_code == 201
    assert forged.json()["data"]["created_by"] == 1
    line = {"supplier_ingredient_id": 1, "ordered_quantity": "0.5", "expected_unit_price": "1"}
    assert stock_client.post(ORDERS, json=order_payload(items=[line])).status_code == 400
    line["ordered_quantity"] = "1"
    assert stock_client.post(ORDERS, json=order_payload(items=[line, line])).status_code == 400


@pytest.mark.parametrize(
    "model, field, value",
    [
        (Ingredient, "status", "INACTIVE"),
        (Unit, "is_active", False),
        (SupplierIngredient, "is_active", False),
    ],
)
def test_inactive_references_rejected(stock_client, stock_session, model, field, value):
    row = stock_session.get(model, 1)
    setattr(row, field, value)
    stock_session.commit()
    assert stock_client.post(ORDERS, json=order_payload()).status_code == 400


def test_snapshot_not_changed_by_supplier_catalog_updates(stock_client, stock_session):
    order = create_order(stock_client)
    mapping = stock_session.get(SupplierIngredient, 1)
    mapping.base_qty_per_purchase_unit = Decimal("500")
    mapping.purchase_unit_id = 3
    mapping.latest_unit_price = Decimal("999")
    stock_session.commit()
    ordered = order_stock(stock_client, order["purchase_order_id"])
    item = ordered["items"][0]
    assert Decimal(item["base_qty_per_purchase_unit"]) == Decimal("1000")
    assert Decimal(item["expected_unit_price"]) == Decimal("35000.25")
    assert item["purchase_unit_id"] == 2


def test_conversion_precision_and_overflow_rollback(stock_client, stock_session):
    mapping = stock_session.get(SupplierIngredient, 1)
    mapping.base_qty_per_purchase_unit = Decimal("0.001")
    stock_session.commit()
    line = {"supplier_ingredient_id": 1, "ordered_quantity": "1.001", "expected_unit_price": "1"}
    assert stock_client.post(ORDERS, json=order_payload(items=[line])).status_code == 400
    mapping = stock_session.get(SupplierIngredient, 1)
    mapping.base_qty_per_purchase_unit = Decimal("99999999999.999")
    stock_session.commit()
    assert stock_client.post(ORDERS, json=order_payload()).status_code == 400
    assert stock_session.scalar(select(func.count()).select_from(PurchaseOrder)) == 0


def test_duplicate_number_rolls_back_and_invalid_update_preserves_draft(stock_client):
    order = create_order(stock_client, purchase_order_number="PO-DUP")
    assert (
        stock_client.post(
            ORDERS,
            json=order_payload(
                purchase_order_number="PO-DUP",
            ),
        ).status_code
        == 409
    )
    order_id = order["purchase_order_id"]
    assert (
        stock_client.patch(
            f"{ORDERS}/{order_id}",
            json={
                "order_date": "2026-10-01",
            },
        ).status_code
        == 400
    )
    assert stock_client.get(f"{ORDERS}/{order_id}").json()["data"]["order_date"] == "2026-09-01"
    assert stock_client.get(ORDERS).json()["data"]["total"] == 1


def test_order_lock_compiles_for_postgresql_and_refreshes_state():
    class Capture:
        def scalar(self, statement):
            self.statement = statement

    capture = Capture()
    PurchaseOrderRepository.get(capture, 1, lock=True)
    assert "FOR UPDATE" in str(capture.statement.compile(dialect=postgresql.dialect()))
    assert capture.statement.get_execution_options()["populate_existing"] is True
