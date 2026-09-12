"""Offline API integration tests with real SQLAlchemy transactions.

SQLite ignores SELECT FOR UPDATE, so PostgreSQL lock statements are checked
separately. Only cloned test metadata receives SQLite identity types and the
partial unique index already present in the PostgreSQL DDL.
"""

from collections.abc import Generator
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, Index, Integer, MetaData, create_engine, event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.core.config import Settings
from app.db.models.catalog import (
    Dish,
    Ingredient,
    MenuCategory,
    RecipeItem,
    RecipeVersion,
    Unit,
    UnitConversion,
)
from app.db.models.rbac import User
from app.db.session import get_db

PREFIX = "/api/v1/recipes"


@pytest.fixture
def recipe_engine() -> Generator[Engine, None, None]:
    metadata = MetaData()
    for model in (
        User,
        MenuCategory,
        Dish,
        Unit,
        UnitConversion,
        Ingredient,
        RecipeVersion,
        RecipeItem,
    ):
        table = model.__table__.to_metadata(metadata)
        for column in table.primary_key:
            if isinstance(column.type, BigInteger):
                column.type = Integer()

    versions = metadata.tables["restaurant_ai.recipe_versions"]
    Index(
        "uq_recipe_versions_one_active_per_dish",
        versions.c.dish_id,
        unique=True,
        sqlite_where=versions.c.status == "ACTIVE",
    )
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        execution_options={"schema_translate_map": {"restaurant_ai": None}},
    )
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def recipe_session(recipe_engine: Engine) -> Generator[Session, None, None]:
    with Session(recipe_engine, autoflush=False) as session:
        session.add(MenuCategory(category_id=1, category_code="FOOD", category_name="Food"))
        session.add_all(
            Unit(
                unit_id=unit_id,
                unit_code=code,
                unit_name=code,
                dimension=dimension,
                is_active=unit_id != 8,
            )
            for unit_id, code, dimension in (
                (1, "G", "MASS"),
                (2, "KG", "MASS"),
                (3, "ML", "VOLUME"),
                (4, "L", "VOLUME"),
                (5, "PIECE", "COUNT"),
                (6, "OZ", "MASS"),
                (7, "MG", "MASS"),
                (8, "OLD_G", "MASS"),
            )
        )
        session.flush()
        session.add_all(
            Dish(
                dish_id=dish_id,
                dish_code=f"DISH_{dish_id}",
                dish_name=f"Dish {dish_id}",
                category_id=1,
                selling_price=Decimal("100.00"),
                status=status,
            )
            for dish_id, status in ((1, "ACTIVE"), (2, "ACTIVE"), (3, "INACTIVE"), (4, "SOLD_OUT"))
        )
        session.add_all(
            Ingredient(
                ingredient_id=ingredient_id,
                ingredient_code=code,
                ingredient_name=code.title(),
                base_unit_id=base_unit_id,
                status=status,
            )
            for ingredient_id, code, base_unit_id, status in (
                (1, "FLOUR", 1, "ACTIVE"),
                (2, "MILK", 3, "ACTIVE"),
                (3, "OLD_SALT", 1, "INACTIVE"),
                (4, "SUGAR", 1, "ACTIVE"),
            )
        )
        session.add_all(
            UnitConversion(
                conversion_id=conversion_id,
                from_unit_id=from_unit,
                to_unit_id=to_unit,
                factor=Decimal("1000"),
            )
            for conversion_id, from_unit, to_unit in ((1, 2, 1), (2, 4, 3), (3, 1, 7))
        )
        session.commit()
        yield session


@pytest.fixture
def recipe_client(
    recipe_session: Session, monkeypatch: pytest.MonkeyPatch
) -> Generator[TestClient, None, None]:
    settings = Settings(_env_file=None, DATABASE_URL=None, DEBUG=False)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    app = main_module.create_app()
    app.dependency_overrides[get_db] = lambda: recipe_session
    with TestClient(app) as client:
        yield client


def seed_recipe(
    session: Session,
    recipe_id: int = 1,
    *,
    dish_id: int = 1,
    version_no: int | None = None,
    status: str = "DRAFT",
    effective_from: date | None = None,
    effective_to: date | None = None,
    with_item: bool = False,
) -> RecipeVersion:
    recipe = RecipeVersion(
        recipe_version_id=recipe_id,
        dish_id=dish_id,
        version_no=version_no if version_no is not None else recipe_id,
        status=status,
        effective_from=effective_from,
        effective_to=effective_to,
        notes="Original notes",
        created_by=None,
    )
    session.add(recipe)
    session.flush()
    if with_item:
        session.add(
            RecipeItem(
                recipe_version_id=recipe_id,
                ingredient_id=1,
                unit_id=1,
                quantity=Decimal("10.000"),
                base_quantity=Decimal("10.000"),
            )
        )
    session.commit()
    return recipe


def item(ingredient_id: int = 1, unit_id: int = 1, quantity: str = "120.000") -> dict:
    return {"ingredient_id": ingredient_id, "unit_id": unit_id, "quantity": quantity}


def assert_error(response, status_code: int) -> None:
    assert response.status_code == status_code, response.text
    body = response.json()
    assert set(body) == {"success", "message", "data"}
    assert body["success"] is False
    assert body["data"] is None
    assert isinstance(body["message"], str) and body["message"]


def stored_items(engine: Engine, recipe_id: int = 1) -> list[tuple]:
    with Session(engine) as verification:
        return list(
            verification.execute(
                select(
                    RecipeItem.recipe_item_id,
                    RecipeItem.ingredient_id,
                    RecipeItem.unit_id,
                    RecipeItem.quantity,
                    RecipeItem.base_quantity,
                )
                .where(RecipeItem.recipe_version_id == recipe_id)
                .order_by(RecipeItem.recipe_item_id)
            ).all()
        )


def test_recipe_list_paginates_and_reports_total(recipe_client, recipe_session):
    for recipe_id in range(1, 5):
        seed_recipe(recipe_session, recipe_id)

    response = recipe_client.get(PREFIX, params={"limit": 2, "offset": 1})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 4
    assert data["limit"] == 2
    assert data["offset"] == 1
    assert len(data["items"]) == 2
    assert [recipe["recipe_version_id"] for recipe in data["items"]] == [2, 3]
    empty_page = recipe_client.get(PREFIX, params={"offset": 10}).json()["data"]
    assert empty_page["total"] == 4
    assert empty_page["items"] == []


@pytest.mark.parametrize(
    ("filters", "expected_ids"),
    [
        ({"dish_id": 1}, {1, 2}),
        ({"status": "DRAFT"}, {2, 3}),
        ({"dish_id": 1, "status": "DRAFT"}, {2}),
        ({"dish_id": 2, "status": "ACTIVE"}, set()),
    ],
)
def test_recipe_list_filters(recipe_client, recipe_session, filters, expected_ids):
    seed_recipe(recipe_session, 1, status="ACTIVE")
    seed_recipe(recipe_session, 2)
    seed_recipe(recipe_session, 3, dish_id=2)

    response = recipe_client.get(PREFIX, params=filters)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == len(expected_ids)
    assert {recipe["recipe_version_id"] for recipe in data["items"]} == expected_ids


@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"status": "BAD"}]
)
def test_recipe_list_rejects_invalid_query(recipe_client, params):
    assert_error(recipe_client.get(PREFIX, params=params), 422)


def test_recipe_detail_includes_all_items_and_units_without_n_plus_one(
    recipe_client, recipe_session, recipe_engine
):
    seed_recipe(recipe_session, with_item=True)
    recipe_session.add(
        RecipeItem(
            recipe_version_id=1,
            ingredient_id=2,
            unit_id=4,
            quantity=Decimal("0.125"),
            base_quantity=Decimal("125.000"),
        )
    )
    recipe_session.commit()
    recipe_session.expunge_all()
    queries = []

    def record_select(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    event.listen(recipe_engine, "before_cursor_execute", record_select)
    try:
        response = recipe_client.get(f"{PREFIX}/1")
    finally:
        event.remove(recipe_engine, "before_cursor_execute", record_select)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["dish"]["dish_id"] == 1
    assert data["dish"]["dish_name"] == "Dish 1"
    assert data["created_by"] is None
    assert data["created_at"]
    items = {entry["ingredient_id"]: entry for entry in data["items"]}
    assert set(items) == {1, 2}
    assert items[1]["ingredient"]["ingredient_name"] == "Flour"
    assert items[1]["ingredient"]["base_unit"]["unit_code"] == "G"
    assert items[2]["unit"]["unit_code"] == "L"
    assert Decimal(items[2]["quantity"]) == Decimal("0.125")
    assert Decimal(items[2]["base_quantity"]) == Decimal("125.000")
    assert len(queries) <= 3, queries


@pytest.mark.parametrize(
    ("start_days", "end_days"), [(None, None), (-1, 1), (0, 0), (None, 0), (0, None)]
)
def test_recipe_active_route_accepts_inclusive_effective_dates(
    recipe_client, recipe_session, start_days, end_days
):
    today = date.today()
    seed_recipe(
        recipe_session,
        status="ACTIVE",
        effective_from=None if start_days is None else today + timedelta(days=start_days),
        effective_to=None if end_days is None else today + timedelta(days=end_days),
        with_item=True,
    )

    response = recipe_client.get(f"{PREFIX}/dishes/1/active")

    assert response.status_code == 200
    assert response.json()["data"]["recipe_version_id"] == 1
    assert response.json()["data"]["status"] == "ACTIVE"
    assert len(response.json()["data"]["items"]) == 1


@pytest.mark.parametrize(("start_days", "end_days"), [(1, None), (None, -1)])
def test_recipe_active_route_excludes_future_or_expired_dates(
    recipe_client, recipe_session, start_days, end_days
):
    today = date.today()
    seed_recipe(
        recipe_session,
        status="ACTIVE",
        effective_from=None if start_days is None else today + timedelta(days=start_days),
        effective_to=None if end_days is None else today + timedelta(days=end_days),
    )

    assert_error(recipe_client.get(f"{PREFIX}/dishes/1/active"), 404)


def test_recipe_active_route_returns_404_for_missing_dish(recipe_client):
    assert_error(recipe_client.get(f"{PREFIX}/dishes/999/active"), 404)


@pytest.mark.parametrize("status", [None, "DRAFT", "INACTIVE", "EXPIRED"])
def test_recipe_active_route_returns_404_without_active_recipe(
    recipe_client, recipe_session, status
):
    if status is not None:
        seed_recipe(recipe_session, status=status)
    assert_error(recipe_client.get(f"{PREFIX}/dishes/1/active"), 404)


def test_recipe_detail_returns_standard_404(recipe_client):
    assert_error(recipe_client.get(f"{PREFIX}/999"), 404)


def test_recipe_create_uses_next_version_and_server_owned_fields(recipe_client, recipe_session):
    seed_recipe(recipe_session, 1, version_no=1)
    seed_recipe(recipe_session, 2, version_no=4, status="INACTIVE")
    seed_recipe(recipe_session, 3, dish_id=2, version_no=20)

    response = recipe_client.post(PREFIX, json={"dish_id": 1, "notes": "New version"})

    assert response.status_code == 201, response.text
    assert response.json()["success"] is True
    data = response.json()["data"]
    assert data["version_no"] == 5
    assert data["status"] == "DRAFT"
    assert data["created_by"] is None
    assert data["notes"] == "New version"
    assert data["items"] == []
    second = recipe_client.post(PREFIX, json={"dish_id": 1})
    assert second.status_code == 201
    assert second.json()["data"]["version_no"] == 6


def test_recipe_create_first_version_is_one(recipe_client):
    response = recipe_client.post(PREFIX, json={"dish_id": 1})
    assert response.status_code == 201
    assert response.json()["data"]["version_no"] == 1


@pytest.mark.parametrize("dish_id", [3, 4])
def test_recipe_create_rejects_inactive_or_sold_out_dish(recipe_client, dish_id):
    assert_error(recipe_client.post(PREFIX, json={"dish_id": dish_id}), 400)


def test_recipe_create_rejects_missing_dish(recipe_client):
    assert_error(recipe_client.post(PREFIX, json={"dish_id": 999}), 404)


@pytest.mark.parametrize(
    ("field", "value"),
    [("status", "ACTIVE"), ("created_by", 1), ("created_by", None), ("version_no", 9)],
)
def test_recipe_create_rejects_server_owned_fields(recipe_client, field, value):
    assert_error(recipe_client.post(PREFIX, json={"dish_id": 1, field: value}), 422)


def test_recipe_create_rejects_inverted_dates(recipe_client):
    assert_error(
        recipe_client.post(
            PREFIX,
            json={"dish_id": 1, "effective_from": "2026-09-12", "effective_to": "2026-09-11"},
        ),
        422,
    )


def test_recipe_patch_updates_draft_metadata_and_can_clear_dates(recipe_client, recipe_session):
    seed_recipe(recipe_session)
    response = recipe_client.patch(
        f"{PREFIX}/1",
        json={"effective_from": "2026-09-12", "effective_to": "2026-09-13", "notes": "Updated"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["effective_from"] == "2026-09-12"
    assert data["effective_to"] == "2026-09-13"
    assert data["notes"] == "Updated"
    assert data["version_no"] == 1 and data["dish_id"] == 1 and data["status"] == "DRAFT"
    cleared = recipe_client.patch(f"{PREFIX}/1", json={"effective_from": None, "notes": None})
    assert cleared.status_code == 200
    assert cleared.json()["data"]["effective_from"] is None
    assert cleared.json()["data"]["effective_to"] == "2026-09-13"
    assert cleared.json()["data"]["notes"] is None


@pytest.mark.parametrize("status", ["ACTIVE", "INACTIVE", "EXPIRED"])
def test_recipe_patch_requires_draft(recipe_client, recipe_session, status):
    seed_recipe(recipe_session, status=status)
    assert_error(recipe_client.patch(f"{PREFIX}/1", json={"notes": "Forbidden"}), 409)


@pytest.mark.parametrize(
    ("field", "value"), [("dish_id", 2), ("version_no", 2), ("status", "ACTIVE"), ("created_by", 1)]
)
def test_recipe_patch_rejects_immutable_fields(recipe_client, recipe_session, field, value):
    seed_recipe(recipe_session)
    assert_error(recipe_client.patch(f"{PREFIX}/1", json={field: value}), 422)


@pytest.mark.parametrize(
    "changes", [{"effective_to": "2026-09-11"}, {"effective_from": "2026-09-14"}]
)
def test_recipe_patch_validates_merged_dates_and_rolls_back(
    recipe_client, recipe_session, recipe_engine, changes
):
    seed_recipe(recipe_session, effective_from=date(2026, 9, 12), effective_to=date(2026, 9, 13))
    assert_error(recipe_client.patch(f"{PREFIX}/1", json={**changes, "notes": "Wrong"}), 400)
    with Session(recipe_engine) as verification:
        recipe = verification.get(RecipeVersion, 1)
        assert recipe.effective_from == date(2026, 9, 12)
        assert recipe.effective_to == date(2026, 9, 13)
        assert recipe.notes == "Original notes"


@pytest.mark.parametrize(
    "items",
    [
        [],
        [item(), item(quantity="5.000")],
        [item(quantity="0")],
        [item(quantity="-0.001")],
        [item(quantity="1.0001")],
        [item(quantity="100000000000.000")],
        [{**item(), "base_quantity": "120.000"}],
    ],
    ids=["empty", "duplicate", "zero", "negative", "scale", "overflow", "base_quantity"],
)
def test_recipe_items_rejects_invalid_payload(recipe_client, recipe_session, items):
    seed_recipe(recipe_session)
    assert_error(recipe_client.put(f"{PREFIX}/1/items", json={"items": items}), 422)


@pytest.mark.parametrize(
    ("ingredient_id", "unit_id", "status_code"),
    [(999, 1, 404), (1, 999, 404), (3, 1, 400), (1, 8, 400), (1, 3, 400), (1, 6, 400), (1, 7, 400)],
    ids=[
        "missing_ingredient",
        "missing_unit",
        "inactive_ingredient",
        "inactive_unit",
        "dimension",
        "conversion",
        "reverse_conversion",
    ],
)
def test_recipe_items_rejects_invalid_references_and_conversion(
    recipe_client, recipe_session, ingredient_id, unit_id, status_code
):
    seed_recipe(recipe_session)
    assert_error(
        recipe_client.put(f"{PREFIX}/1/items", json={"items": [item(ingredient_id, unit_id)]}),
        status_code,
    )


@pytest.mark.parametrize(
    ("ingredient_id", "unit_id", "quantity", "expected_base"),
    [(1, 1, "120.000", "120.000"), (1, 2, "0.125", "125.000"), (2, 4, "1.250", "1250.000")],
    ids=["base_unit", "kg_to_g", "l_to_ml"],
)
def test_recipe_items_calculates_base_quantity_and_replaces_existing_items(
    recipe_client, recipe_session, recipe_engine, ingredient_id, unit_id, quantity, expected_base
):
    seed_recipe(recipe_session, with_item=True)
    response = recipe_client.put(
        f"{PREFIX}/1/items", json={"items": [item(ingredient_id, unit_id, quantity)]}
    )
    assert response.status_code == 200, response.text
    entries = response.json()["data"]["items"]
    assert len(entries) == 1
    assert entries[0]["ingredient_id"] == ingredient_id
    assert entries[0]["unit_id"] == unit_id
    assert Decimal(entries[0]["quantity"]) == Decimal(quantity)
    assert Decimal(entries[0]["base_quantity"]) == Decimal(expected_base)
    persisted = stored_items(recipe_engine)
    assert len(persisted) == 1
    assert persisted[0][1:] == (ingredient_id, unit_id, Decimal(quantity), Decimal(expected_base))


def test_recipe_items_rounds_half_up_to_database_scale(recipe_client, recipe_session):
    seed_recipe(recipe_session)
    recipe_session.add(UnitConversion(from_unit_id=6, to_unit_id=1, factor=Decimal("1.234500")))
    recipe_session.commit()

    response = recipe_client.put(f"{PREFIX}/1/items", json={"items": [item(1, 6, "1.000")]})

    assert response.status_code == 200
    assert Decimal(response.json()["data"]["items"][0]["base_quantity"]) == Decimal("1.235")


@pytest.mark.parametrize(
    ("factor", "quantity"), [("1000", "99999999999.999"), ("0.000001", "0.001")]
)
def test_recipe_items_rejects_unrepresentable_base_quantity(
    recipe_client, recipe_session, factor, quantity
):
    seed_recipe(recipe_session)
    recipe_session.add(UnitConversion(from_unit_id=6, to_unit_id=1, factor=Decimal(factor)))
    recipe_session.commit()
    assert_error(
        recipe_client.put(f"{PREFIX}/1/items", json={"items": [item(1, 6, quantity)]}), 400
    )


@pytest.mark.parametrize("status", ["ACTIVE", "INACTIVE", "EXPIRED"])
def test_recipe_items_requires_draft(recipe_client, recipe_session, status):
    seed_recipe(recipe_session, status=status)
    assert_error(recipe_client.put(f"{PREFIX}/1/items", json={"items": [item()]}), 409)


def test_recipe_items_rolls_back_all_changes_when_later_item_is_invalid(
    recipe_client, recipe_session, recipe_engine
):
    seed_recipe(recipe_session, with_item=True)
    before = stored_items(recipe_engine)
    response = recipe_client.put(
        f"{PREFIX}/1/items", json={"items": [item(2, 4, "0.125"), item(999, 1)]}
    )
    assert_error(response, 404)
    assert not recipe_session.in_transaction()
    assert stored_items(recipe_engine) == before


def test_recipe_activation_rejects_empty_draft(recipe_client, recipe_session):
    seed_recipe(recipe_session)
    assert_error(recipe_client.post(f"{PREFIX}/1/activate"), 400)


@pytest.mark.parametrize("status", ["ACTIVE", "INACTIVE", "EXPIRED"])
def test_recipe_activation_requires_draft(recipe_client, recipe_session, status):
    seed_recipe(recipe_session, status=status, with_item=True)
    assert_error(recipe_client.post(f"{PREFIX}/1/activate"), 409)


@pytest.mark.parametrize("dish_id", [3, 4])
def test_recipe_activation_rechecks_dish_status(recipe_client, recipe_session, dish_id):
    seed_recipe(recipe_session, dish_id=dish_id, with_item=True)
    assert_error(recipe_client.post(f"{PREFIX}/1/activate"), 400)


def test_recipe_activation_switches_active_atomically_and_preserves_history(
    recipe_client, recipe_session, recipe_engine
):
    seed_recipe(recipe_session, 1, status="ACTIVE", with_item=True)
    seed_recipe(recipe_session, 2, with_item=True)
    seed_recipe(recipe_session, 3, dish_id=2, status="ACTIVE")
    history = stored_items(recipe_engine, 1)
    commits = []

    def record_commit(session):
        commits.append(True)

    event.listen(recipe_session, "after_commit", record_commit)
    response = recipe_client.post(f"{PREFIX}/2/activate")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "ACTIVE"
    assert response.json()["data"]["effective_from"] == date.today().isoformat()
    assert len(commits) == 1
    with Session(recipe_engine) as verification:
        assert verification.get(RecipeVersion, 1).status == "INACTIVE"
        assert verification.get(RecipeVersion, 2).status == "ACTIVE"
        assert verification.get(RecipeVersion, 3).status == "ACTIVE"
        assert len(list(verification.scalars(select(RecipeVersion)))) == 3
    assert stored_items(recipe_engine, 1) == history
    active_response = recipe_client.get(f"{PREFIX}/dishes/1/active")
    assert active_response.json()["data"]["recipe_version_id"] == 2


def test_recipe_activation_preserves_explicit_effective_from(recipe_client, recipe_session):
    start = date.today() - timedelta(days=5)
    seed_recipe(recipe_session, effective_from=start, with_item=True)
    response = recipe_client.post(f"{PREFIX}/1/activate")
    assert response.status_code == 200
    assert response.json()["data"]["effective_from"] == start.isoformat()


def test_recipe_activation_validates_dates_after_defaulting_start(recipe_client, recipe_session):
    seed_recipe(recipe_session, effective_to=date.today() - timedelta(days=1), with_item=True)
    assert_error(recipe_client.post(f"{PREFIX}/1/activate"), 400)
    recipe = recipe_session.get(RecipeVersion, 1)
    assert recipe.status == "DRAFT"
    assert recipe.effective_from is None


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("patch", "/999", {"notes": "Missing"}),
        ("put", "/999/items", {"items": [item()]}),
        ("post", "/999/activate", None),
    ],
)
def test_recipe_mutations_return_standard_404(recipe_client, method, path, payload):
    assert_error(recipe_client.request(method, PREFIX + path, json=payload), 404)


def integrity_failure() -> IntegrityError:
    return IntegrityError("private SQL statement", {}, Exception("private connection string"))


@pytest.mark.parametrize("failure_point", ["flush", "commit"])
def test_recipe_create_rolls_back_integrity_errors_and_hides_database_details(
    recipe_client, recipe_session, recipe_engine, monkeypatch, failure_point
):
    seed_recipe(recipe_session)

    def fail(*args, **kwargs):
        raise integrity_failure()

    with monkeypatch.context() as patch:
        patch.setattr(recipe_session, failure_point, fail)
        response = recipe_client.post(PREFIX, json={"dish_id": 1})

    assert_error(response, 409)
    assert "private" not in response.text
    assert not recipe_session.in_transaction()
    with Session(recipe_engine) as verification:
        assert len(list(verification.scalars(select(RecipeVersion)))) == 1
    retry = recipe_client.post(PREFIX, json={"dish_id": 1})
    assert retry.status_code == 201
    assert retry.json()["data"]["version_no"] == 2


def test_recipe_items_rolls_back_delete_and_insert_on_database_failure(
    recipe_client, recipe_session, recipe_engine, monkeypatch
):
    seed_recipe(recipe_session, with_item=True)
    before = stored_items(recipe_engine)
    real_flush = recipe_session.flush
    flushed_changes = []

    def fail_after_item_flush(*args, **kwargs):
        changed = any(isinstance(entity, RecipeItem) for entity in recipe_session.new)
        real_flush(*args, **kwargs)
        if changed:
            flushed_changes.append(True)
            raise integrity_failure()

    with monkeypatch.context() as patch:
        patch.setattr(recipe_session, "flush", fail_after_item_flush)
        response = recipe_client.put(f"{PREFIX}/1/items", json={"items": [item(2, 4, "0.125")]})

    assert_error(response, 409)
    assert flushed_changes
    assert not recipe_session.in_transaction()
    assert stored_items(recipe_engine) == before


@pytest.mark.parametrize("failure_point", ["activation_flush", "commit"])
def test_recipe_activation_rolls_back_old_and_new_statuses_on_integrity_error(
    recipe_client, recipe_session, recipe_engine, monkeypatch, failure_point
):
    seed_recipe(recipe_session, 1, status="ACTIVE", with_item=True)
    seed_recipe(recipe_session, 2, with_item=True)
    real_flush = recipe_session.flush
    failed = []

    def fail_activation_flush(*args, **kwargs):
        activating = any(
            isinstance(entity, RecipeVersion)
            and entity.recipe_version_id == 2
            and entity.status == "ACTIVE"
            for entity in recipe_session.dirty
        )
        real_flush(*args, **kwargs)
        if activating:
            failed.append(True)
            raise integrity_failure()

    def fail_commit():
        failed.append(True)
        raise integrity_failure()

    with monkeypatch.context() as patch:
        if failure_point == "activation_flush":
            patch.setattr(recipe_session, "flush", fail_activation_flush)
        else:
            patch.setattr(recipe_session, "commit", fail_commit)
        response = recipe_client.post(f"{PREFIX}/2/activate")

    assert_error(response, 409)
    assert failed
    assert "private" not in response.text
    assert not recipe_session.in_transaction()
    with Session(recipe_engine) as verification:
        assert verification.get(RecipeVersion, 1).status == "ACTIVE"
        replacement = verification.get(RecipeVersion, 2)
        assert replacement.status == "DRAFT"
        assert replacement.effective_from is None
    retry = recipe_client.post(f"{PREFIX}/2/activate")
    assert retry.status_code == 200


def test_recipe_creation_locks_dish_and_activation_locks_all_dish_versions(
    recipe_client, recipe_session
):
    seed_recipe(recipe_session, 1, status="ACTIVE", with_item=True)
    seed_recipe(recipe_session, 2, with_item=True)
    locks = []

    def record_lock(orm_execute_state):
        statement = orm_execute_state.statement
        if getattr(statement, "_for_update_arg", None) is not None:
            locks.append(str(statement.compile(dialect=postgresql.dialect())))

    event.listen(recipe_session, "do_orm_execute", record_lock)
    created = recipe_client.post(PREFIX, json={"dish_id": 1})
    assert created.status_code == 201
    assert any("FROM restaurant_ai.dishes" in sql and "FOR UPDATE" in sql for sql in locks)
    locks.clear()
    activated = recipe_client.post(f"{PREFIX}/2/activate")
    assert activated.status_code == 200
    assert any("FROM restaurant_ai.dishes" in sql and "FOR UPDATE" in sql for sql in locks)
    assert any(
        "FROM restaurant_ai.recipe_versions" in sql
        and "recipe_versions.dish_id =" in sql
        and "FOR UPDATE" in sql
        for sql in locks
    )
    assert "FROM restaurant_ai.dishes" in locks[0]
    assert "ORDER BY restaurant_ai.recipe_versions.recipe_version_id" in locks[1]


def test_recipe_activation_flushes_old_active_before_lower_id_target(
    recipe_client, recipe_session, recipe_engine
):
    # SQLAlchemy normally updates rows in PK order. A single flush would try
    # to activate 1 while 2 is still ACTIVE and violate the partial unique index.
    seed_recipe(recipe_session, 1, with_item=True)
    seed_recipe(recipe_session, 2, status="ACTIVE", with_item=True)

    response = recipe_client.post(f"{PREFIX}/1/activate")

    assert response.status_code == 200, response.text
    with Session(recipe_engine) as verification:
        assert verification.get(RecipeVersion, 1).status == "ACTIVE"
        assert verification.get(RecipeVersion, 2).status == "INACTIVE"


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "", None),
        ("get", "/1", None),
        ("get", "/dishes/1/active", None),
        ("post", "", {"dish_id": 1}),
    ],
)
def test_recipe_database_failures_are_sanitized_even_in_debug_mode(
    recipe_client, recipe_session, monkeypatch, method, path, payload
):
    recipe_client.app.debug = True

    def fail_query(*args, **kwargs):
        raise OperationalError("private SQL", {}, Exception("private connection string"))

    with monkeypatch.context() as patch:
        patch.setattr(recipe_session, "scalar", fail_query)
        response = recipe_client.request(method, PREFIX + path, json=payload)

    assert_error(response, 503)
    assert "private" not in response.text
    assert "Traceback" not in response.text
    assert not recipe_session.in_transaction()


def test_recipe_items_rejects_inactive_base_unit(recipe_client, recipe_session):
    seed_recipe(recipe_session, with_item=True)
    recipe_session.get(Unit, 1).is_active = False
    recipe_session.commit()

    assert_error(recipe_client.put(f"{PREFIX}/1/items", json={"items": [item(1, 2)]}), 400)
