"""Stocktake workflow tests use the existing schema in an isolated SQLite database."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.db.models.inventory import StockLot, StockMovement, Stocktake, StocktakeItem
from app.modules.inventory.stock_schemas import StockAdjustment
from app.modules.inventory.stock_service import StockService
from app.modules.inventory.stocktake_repository import StocktakeRepository
from app.modules.inventory.stocktake_schemas import (
    StocktakeComplete,
    StocktakeCount,
    StocktakeCreate,
    StocktakeStart,
)
from app.modules.inventory.stocktake_service import StocktakeService

BASE = "/api/v1/inventory/stocktakes"


@pytest.fixture
def stocktake_lots(stock_session):
    for lot_id, ingredient_id, quantity in ((201, 1, "50.000"), (202, 2, "20.000")):
        stock_session.add(
            StockLot(
                stock_lot_id=lot_id,
                ingredient_id=ingredient_id,
                lot_code=f"COUNT-{lot_id}",
                received_quantity=Decimal("100.000"),
                current_quantity=Decimal(quantity),
                unit_cost=Decimal("1.0000"),
                status="ACTIVE",
            )
        )
    stock_session.commit()


def begin_count(session, lot_ids=(201, 202)):
    service = StocktakeService()
    draft = service.create(session, StocktakeCreate(created_by=1))
    return service.start(session, draft.stocktake_id, StocktakeStart(stock_lot_ids=list(lot_ids)))


def record_counts(session, stocktake, counts):
    service = StocktakeService()
    for item, quantity in zip(stocktake.items, counts, strict=True):
        stocktake = service.count(
            session,
            stocktake.stocktake_id,
            item.stocktake_item_id,
            StocktakeCount(actual_quantity=Decimal(quantity), adjustment_reason="Verified count"),
        )
    return stocktake


def persisted(engine, stocktake_id):
    with Session(engine) as session:
        stocktake = session.get(Stocktake, stocktake_id)
        quantities = list(
            session.scalars(
                select(StockLot.current_quantity)
                .where(StockLot.stock_lot_id.in_([201, 202]))
                .order_by(StockLot.stock_lot_id)
            )
        )
        movements = session.scalar(select(func.count()).select_from(StockMovement))
        return stocktake.status, quantities, movements


def test_stocktake_adjusts_both_directions_once_with_source_links(
    stock_session, stock_engine, stocktake_lots
):
    started = begin_count(stock_session)
    assert started.status == "IN_PROGRESS"
    assert [item.system_quantity for item in started.items] == [Decimal("50"), Decimal("20")]
    assert all(not item.counted and item.adjustment_reason is None for item in started.items)
    counted = record_counts(stock_session, started, ["45", "23"])
    assert [item.variance_quantity for item in counted.items] == [Decimal("-5"), Decimal("3")]
    # Recording counts only writes the count sheet, not stock or movements.
    assert persisted(stock_engine, started.stocktake_id) == (
        "IN_PROGRESS",
        [Decimal("50"), Decimal("20")],
        0,
    )

    service = StocktakeService()
    completed = service.complete(
        stock_session, started.stocktake_id, StocktakeComplete(completed_by=1)
    )
    assert completed.status == "COMPLETED"
    assert completed.completed_by == 1
    assert completed.completed_at >= completed.started_at
    repeated = service.complete(
        stock_session, started.stocktake_id, StocktakeComplete(completed_by=1)
    )
    assert repeated == completed
    assert persisted(stock_engine, started.stocktake_id) == (
        "COMPLETED",
        [Decimal("45"), Decimal("23")],
        2,
    )
    with Session(stock_engine) as verify:
        movements = list(
            verify.scalars(select(StockMovement).order_by(StockMovement.stock_movement_id))
        )
        assert [(row.direction, row.quantity) for row in movements] == [
            ("OUT", Decimal("5")),
            ("IN", Decimal("3")),
        ]
        assert [row.stocktake_item_id for row in movements] == [
            item.stocktake_item_id for item in started.items
        ]
        assert all(row.movement_type == "ADJUSTMENT" and row.performed_by == 1 for row in movements)
        assert all(row.reason == "Verified count" for row in movements)


def test_unchanged_snapshot_does_not_count_as_explicit_verification(
    stock_session, stock_engine, stocktake_lots
):
    started = begin_count(stock_session)
    service = StocktakeService()
    with pytest.raises(ConflictError, match="explicitly recorded count"):
        service.complete(stock_session, started.stocktake_id, StocktakeComplete(completed_by=1))
    first = started.items[0]
    service.count(
        stock_session,
        started.stocktake_id,
        first.stocktake_item_id,
        StocktakeCount(actual_quantity=Decimal("50"), adjustment_reason="Count verified"),
    )
    with pytest.raises(ConflictError, match="explicitly recorded count"):
        service.complete(stock_session, started.stocktake_id, StocktakeComplete(completed_by=1))
    counted = record_counts(stock_session, started, ["50", "20"])
    assert all(item.counted for item in counted.items)
    service.complete(stock_session, started.stocktake_id, StocktakeComplete(completed_by=1))
    assert persisted(stock_engine, started.stocktake_id) == (
        "COMPLETED",
        [Decimal("50"), Decimal("20")],
        0,
    )


def test_complete_rolls_back_stock_ledger_and_status_after_database_failure(
    stock_session, stock_engine, stocktake_lots
):
    started = record_counts(stock_session, begin_count(stock_session), ["40", "10"])

    def fail_after_movement_flush(session, flush_context):
        if any(isinstance(row, StockMovement) for row in session.new):
            raise IntegrityError(
                "injected offline failure", {}, Exception("private storage detail")
            )

    event.listen(stock_session, "after_flush", fail_after_movement_flush)
    try:
        with pytest.raises(ConflictError, match="Stock data conflicts"):
            StocktakeService().complete(
                stock_session, started.stocktake_id, StocktakeComplete(completed_by=1)
            )
    finally:
        event.remove(stock_session, "after_flush", fail_after_movement_flush)
    assert persisted(stock_engine, started.stocktake_id) == (
        "IN_PROGRESS",
        [Decimal("50"), Decimal("20")],
        0,
    )
    StocktakeService().complete(
        stock_session, started.stocktake_id, StocktakeComplete(completed_by=1)
    )
    assert persisted(stock_engine, started.stocktake_id) == (
        "COMPLETED",
        [Decimal("40"), Decimal("10")],
        2,
    )


def test_quantity_drift_rejects_complete_without_partial_adjustment(
    stock_session, stock_engine, stocktake_lots
):
    started = record_counts(stock_session, begin_count(stock_session), ["45", "18"])
    StockService().adjust(
        stock_session,
        202,
        StockAdjustment(
            actual_quantity=Decimal("19"), performed_by=1, reason="Intervening movement"
        ),
    )
    with pytest.raises(ConflictError, match="Stock changed"):
        StocktakeService().complete(
            stock_session, started.stocktake_id, StocktakeComplete(completed_by=1)
        )
    assert persisted(stock_engine, started.stocktake_id) == (
        "IN_PROGRESS",
        [Decimal("50"), Decimal("19")],
        1,
    )


def test_same_second_net_zero_movements_invalidate_count_window(
    stock_session, stock_engine, stocktake_lots, monkeypatch
):
    # Millisecond timestamps deliberately share the same second. Server SQLite
    # CURRENT_TIMESTAMP defaults would round these below started_at and miss drift.
    start_time = datetime.now(UTC).replace(microsecond=100000)
    monkeypatch.setattr("app.modules.inventory.stocktake_service.stock_now", lambda _: start_time)
    monkeypatch.setattr(
        "app.modules.inventory.stock_common.stock_now",
        lambda _: start_time + timedelta(milliseconds=50),
    )
    started = record_counts(stock_session, begin_count(stock_session), ["45", "20"])
    for quantity in ("49", "50"):
        StockService().adjust(
            stock_session,
            201,
            StockAdjustment(
                actual_quantity=Decimal(quantity), performed_by=1, reason="Moved stock"
            ),
        )
    with pytest.raises(ConflictError, match="Stock moved"):
        StocktakeService().complete(
            stock_session, started.stocktake_id, StocktakeComplete(completed_by=1)
        )
    with pytest.raises(ConflictError, match="Stock moved"):
        record_counts(stock_session, started, ["44", "20"])
    assert persisted(stock_engine, started.stocktake_id) == (
        "IN_PROGRESS",
        [Decimal("50"), Decimal("20")],
        2,
    )


def test_movements_before_start_do_not_invalidate_new_snapshot(stock_session, stocktake_lots):
    StockService().adjust(
        stock_session,
        201,
        StockAdjustment(actual_quantity=Decimal("49"), performed_by=1, reason="Earlier correction"),
    )
    started = begin_count(stock_session)
    assert started.items[0].system_quantity == Decimal("49")
    record_counts(stock_session, started, ["49", "20"])
    assert (
        StocktakeService()
        .complete(stock_session, started.stocktake_id, StocktakeComplete(completed_by=1))
        .status
        == "COMPLETED"
    )


def test_count_above_received_is_rejected_without_changing_original_receipt(
    stock_session, stock_engine, stocktake_lots
):
    started = begin_count(stock_session, [201])
    with pytest.raises(ConflictError, match="original received quantity"):
        record_counts(stock_session, started, ["101"])
    with Session(stock_engine) as verify:
        lot = verify.get(StockLot, 201)
        item = verify.get(StocktakeItem, started.items[0].stocktake_item_id)
        assert lot.received_quantity == Decimal("100")
        assert item.actual_quantity == Decimal("50")
        assert item.adjustment_reason is None
        assert verify.scalar(select(func.count()).select_from(StockLot)) == 2


def test_complete_revalidates_received_limit_before_adjusting_any_lot(
    stock_session, stock_engine, stocktake_lots
):
    started = record_counts(stock_session, begin_count(stock_session), ["40", "30"])
    # A pre-existing/imported count sheet must pass completion-time invariants too.
    stock_session.get(StockLot, 202).received_quantity = Decimal("25")
    stock_session.commit()
    with pytest.raises(ConflictError, match="original received quantity"):
        StocktakeService().complete(
            stock_session, started.stocktake_id, StocktakeComplete(completed_by=1)
        )
    assert persisted(stock_engine, started.stocktake_id) == (
        "IN_PROGRESS",
        [Decimal("50"), Decimal("20")],
        0,
    )


@pytest.mark.parametrize(
    ("initial_status", "count", "expected_status"),
    [
        ("ACTIVE", "0", "DEPLETED"),
        ("DEPLETED", "5", "ACTIVE"),
        ("BLOCKED", "0", "BLOCKED"),
        ("EXPIRED", "5", "EXPIRED"),
    ],
)
def test_stocktake_preserves_restrictions_and_updates_depletion(
    stock_session, stocktake_lots, initial_status, count, expected_status
):
    lot = stock_session.get(StockLot, 201)
    lot.status = initial_status
    if initial_status == "DEPLETED":
        lot.current_quantity = Decimal("0")
    stock_session.commit()
    started = record_counts(stock_session, begin_count(stock_session, [201]), [count])
    StocktakeService().complete(
        stock_session, started.stocktake_id, StocktakeComplete(completed_by=1)
    )
    assert stock_session.get(StockLot, 201).status == expected_status


def test_api_create_start_count_complete_list_and_terminal_state_guards(
    stock_client, stocktake_lots
):
    created = stock_client.post(BASE, json={"created_by": 1, "notes": "Evening count"})
    assert created.status_code == 201, created.text
    draft = created.json()["data"]
    assert draft["status"] == "DRAFT" and draft["items"] == []
    stocktake_id = draft["stocktake_id"]
    assert (
        stock_client.post(f"{BASE}/{stocktake_id}/complete", json={"completed_by": 1}).status_code
        == 409
    )
    started = stock_client.post(f"{BASE}/{stocktake_id}/start", json={"stock_lot_ids": [201]})
    assert started.status_code == 200, started.text
    item_id = started.json()["data"]["items"][0]["stocktake_item_id"]
    counted = stock_client.patch(
        f"{BASE}/{stocktake_id}/items/{item_id}",
        json={"actual_quantity": "48.000", "adjustment_reason": "Two grams missing"},
    )
    assert counted.status_code == 200, counted.text
    assert counted.json()["data"]["items"][0]["variance_quantity"] == "-2.000"
    completed = stock_client.post(f"{BASE}/{stocktake_id}/complete", json={"completed_by": 1})
    assert completed.status_code == 200, completed.text
    repeated = stock_client.post(f"{BASE}/{stocktake_id}/complete", json={"completed_by": 1})
    assert repeated.json() == completed.json()
    listed = stock_client.get(BASE, params={"status": "COMPLETED", "limit": 1})
    assert listed.json()["data"]["total"] == 1
    assert listed.json()["data"]["items"][0]["stocktake_id"] == stocktake_id
    assert stock_client.get(f"{BASE}/{stocktake_id}").json()["data"] == completed.json()["data"]
    assert stock_client.post(f"{BASE}/{stocktake_id}/cancel").status_code == 409
    assert (
        stock_client.post(f"{BASE}/{stocktake_id}/start", json={"stock_lot_ids": [202]}).status_code
        == 409
    )
    assert (
        stock_client.patch(
            f"{BASE}/{stocktake_id}/items/{item_id}",
            json={"actual_quantity": "47", "adjustment_reason": "Late count"},
        ).status_code
        == 409
    )


@pytest.mark.parametrize("start_first", [False, True])
def test_cancel_preserves_stock_and_blocks_further_counting(
    stock_client, stock_engine, stocktake_lots, start_first
):
    stocktake_id = stock_client.post(BASE, json={"created_by": 1}).json()["data"]["stocktake_id"]
    if start_first:
        stock_client.post(f"{BASE}/{stocktake_id}/start", json={"stock_lot_ids": [201, 202]})
    cancelled = stock_client.post(f"{BASE}/{stocktake_id}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["data"]["status"] == "CANCELLED"
    assert stock_client.post(f"{BASE}/{stocktake_id}/cancel").json() == cancelled.json()
    assert (
        stock_client.post(f"{BASE}/{stocktake_id}/complete", json={"completed_by": 1}).status_code
        == 409
    )
    assert (
        stock_client.post(f"{BASE}/{stocktake_id}/start", json={"stock_lot_ids": [201]}).status_code
        == 409
    )
    assert persisted(stock_engine, stocktake_id) == ("CANCELLED", [Decimal("50"), Decimal("20")], 0)


@pytest.mark.parametrize("lot_ids", [[], [201, 201], [0], [-1], [9223372036854775808]])
def test_start_rejects_invalid_lot_selection(stock_client, stocktake_lots, lot_ids):
    stocktake_id = stock_client.post(BASE, json={"created_by": 1}).json()["data"]["stocktake_id"]
    assert (
        stock_client.post(
            f"{BASE}/{stocktake_id}/start", json={"stock_lot_ids": lot_ids}
        ).status_code
        == 422
    )
    assert stock_client.get(f"{BASE}/{stocktake_id}").json()["data"]["status"] == "DRAFT"


def test_missing_lot_rolls_back_start_and_does_not_leave_partial_items(
    stock_client, stocktake_lots
):
    stocktake_id = stock_client.post(BASE, json={"created_by": 1}).json()["data"]["stocktake_id"]
    assert (
        stock_client.post(
            f"{BASE}/{stocktake_id}/start", json={"stock_lot_ids": [201, 999]}
        ).status_code
        == 404
    )
    detail = stock_client.get(f"{BASE}/{stocktake_id}").json()["data"]
    assert detail["status"] == "DRAFT" and detail["started_at"] is None and detail["items"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"actual_quantity": "-1", "adjustment_reason": "Count"},
        {"actual_quantity": "0.0001", "adjustment_reason": "Count"},
        {"actual_quantity": "100000000000", "adjustment_reason": "Count"},
        {"actual_quantity": "NaN", "adjustment_reason": "Count"},
        {"actual_quantity": "Infinity", "adjustment_reason": "Count"},
        {"actual_quantity": "50"},
        {"actual_quantity": "50", "adjustment_reason": "  "},
        {"actual_quantity": "50", "adjustment_reason": "Count", "system_quantity": "60"},
    ],
)
def test_count_validation_is_strict_even_when_quantity_matches_snapshot(
    stock_client, stock_session, stocktake_lots, payload
):
    started = begin_count(stock_session, [201])
    response = stock_client.patch(
        f"{BASE}/{started.stocktake_id}/items/{started.items[0].stocktake_item_id}", json=payload
    )
    assert response.status_code == 422, response.text
    detail = stock_client.get(f"{BASE}/{started.stocktake_id}").json()["data"]
    assert detail["items"][0]["counted"] is False


def test_count_item_must_belong_to_requested_stocktake(stock_client, stock_session, stocktake_lots):
    first = begin_count(stock_session, [201])
    second = begin_count(stock_session, [202])
    response = stock_client.patch(
        f"{BASE}/{first.stocktake_id}/items/{second.items[0].stocktake_item_id}",
        json={"actual_quantity": "10", "adjustment_reason": "Wrong sheet"},
    )
    assert response.status_code == 404
    assert StocktakeService().get(stock_session, second.stocktake_id).items[0].counted is False


def test_missing_actor_duplicate_number_and_missing_stocktake(stock_client, stocktake_lots):
    assert stock_client.post(BASE, json={"created_by": 999}).status_code == 404
    assert (
        stock_client.post(BASE, json={"created_by": 1, "stocktake_number": "COUNT-ONE"}).status_code
        == 201
    )
    duplicate = stock_client.post(BASE, json={"created_by": 1, "stocktake_number": "COUNT-ONE"})
    assert duplicate.status_code == 409
    assert "SQL" not in duplicate.text and "UNIQUE" not in duplicate.text
    assert stock_client.get(f"{BASE}/999").status_code == 404


def test_repository_locks_stocktake_source_and_orders_lot_locks_for_postgresql():
    statements = []

    class CaptureSession:
        def scalar(self, statement):
            statements.append(statement)
            return None

        def scalars(self, statement):
            statements.append(statement)
            return []

    repository = StocktakeRepository()
    repository.get(CaptureSession(), 1, lock=True)
    repository.lots(CaptureSession(), [202, 201], lock=True)
    compiled = [str(statement.compile(dialect=postgresql.dialect())) for statement in statements]
    assert all("FOR UPDATE" in statement for statement in compiled)
    assert "ORDER BY restaurant_ai.stock_lots.stock_lot_id" in compiled[1]
    assert all(statement.get_execution_options()["populate_existing"] for statement in statements)
