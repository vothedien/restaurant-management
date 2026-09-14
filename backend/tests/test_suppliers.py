"""Offline purchasing API tests using real transactions in isolated SQLite.

The test-only metadata reproduces the preferred-supplier partial unique index
from the PostgreSQL DDL. PostgreSQL row locks are checked by SQL compilation;
SQLite cannot exercise concurrent SELECT FOR UPDATE behavior.
"""

from collections.abc import Generator
from datetime import UTC, datetime
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
from app.db.models.catalog import Ingredient, Unit
from app.db.models.inventory import Supplier, SupplierIngredient
from app.db.session import get_db

SUPPLIERS = "/api/v1/purchasing/suppliers"
MAPPINGS = "/api/v1/purchasing/supplier-ingredients"


@pytest.fixture
def purchasing_engine() -> Generator[Engine, None, None]:
    metadata = MetaData()
    for model in (Unit, Ingredient, Supplier, SupplierIngredient):
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
def purchasing_session(purchasing_engine: Engine) -> Generator[Session, None, None]:
    with Session(purchasing_engine, autoflush=False) as session:
        session.add_all(
            Unit(
                unit_id=unit_id,
                unit_code=code,
                unit_name=code.title(),
                dimension=dimension,
                is_active=unit_id != 4,
            )
            for unit_id, code, dimension in (
                (1, "G", "MASS"),
                (2, "KG", "MASS"),
                (3, "BOX", "COUNT"),
                (4, "OLD_KG", "MASS"),
            )
        )
        session.flush()
        session.add_all(
            Ingredient(
                ingredient_id=ingredient_id,
                ingredient_code=code,
                ingredient_name=code.title(),
                base_unit_id=1,
                status=status,
            )
            for ingredient_id, code, status in (
                (1, "FLOUR", "ACTIVE"),
                (2, "SUGAR", "ACTIVE"),
                (3, "OLD_SALT", "INACTIVE"),
            )
        )
        session.add_all(
            Supplier(
                supplier_id=supplier_id,
                supplier_code=code,
                supplier_name=name,
                contact_name=f"Contact {code}",
                phone=f"090000000{supplier_id}",
                email=f"{code.lower()}@example.com",
                status=status,
                created_at=datetime(2020, 1, 1, tzinfo=UTC),
                updated_at=datetime(2020, 1, 1, tzinfo=UTC),
            )
            for supplier_id, code, name, status in (
                (1, "ACME", "Acme Foods", "ACTIVE"),
                (2, "BETA", "Beta Ingredients", "ACTIVE"),
                (3, "CLOSED", "Closed Supplier", "INACTIVE"),
                (4, "PAUSED", "Paused Supplier", "SUSPENDED"),
            )
        )
        session.commit()
        yield session


@pytest.fixture
def purchasing_client(
    purchasing_session: Session, monkeypatch: pytest.MonkeyPatch
) -> Generator[TestClient, None, None]:
    settings = Settings(_env_file=None, DATABASE_URL=None, DEBUG=False)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    app = main_module.create_app()
    app.dependency_overrides[get_db] = lambda: purchasing_session
    with TestClient(app) as client:
        yield client


def supplier_payload(**changes) -> dict:
    return {"supplier_code": " new_supplier ", "supplier_name": " New Supplier ", **changes}


def mapping_payload(**changes) -> dict:
    return {
        "supplier_id": 1,
        "ingredient_id": 1,
        "supplier_sku": "BOT-MI-01",
        "purchase_unit_id": 2,
        "base_qty_per_purchase_unit": "1000.000",
        "lead_time_days": 2,
        "minimum_order_qty": "5.000",
        "latest_unit_price": "28000.00",
        "is_preferred": False,
        "is_active": True,
        **changes,
    }


def seed_mapping(session: Session, mapping_id: int = 1, **changes) -> SupplierIngredient:
    mapping = SupplierIngredient(supplier_ingredient_id=mapping_id, **mapping_payload(**changes))
    session.add(mapping)
    session.commit()
    return mapping


def assert_error(response, status_code: int) -> None:
    assert response.status_code == status_code, response.text
    body = response.json()
    assert set(body) == {"success", "message", "data"}
    assert body["success"] is False
    assert body["data"] is None
    assert isinstance(body["message"], str) and body["message"]
    assert "private" not in response.text
    assert "Traceback" not in response.text


def integrity_failure() -> IntegrityError:
    return IntegrityError("private SQL statement", {}, Exception("private connection string"))


def test_supplier_create_normalizes_code_and_optional_strings(purchasing_client):
    response = purchasing_client.post(
        SUPPLIERS,
        json=supplier_payload(
            contact_name="  Contact Name  ", phone="  ", email=" ", address="\n", tax_code=""
        ),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {"success", "message", "data"}
    assert body["success"] is True
    data = body["data"]
    assert data["supplier_id"] > 0
    assert data["supplier_code"] == "NEW_SUPPLIER"
    assert data["supplier_name"] == "New Supplier"
    assert data["contact_name"] == "Contact Name"
    assert data["status"] == "ACTIVE"
    assert data["created_at"] and data["updated_at"]
    for field in ("phone", "email", "address", "tax_code"):
        assert data[field] is None


def test_supplier_create_rejects_normalized_duplicate(purchasing_client):
    assert_error(
        purchasing_client.post(SUPPLIERS, json=supplier_payload(supplier_code=" acme ")), 409
    )


def test_supplier_accepts_exact_model_string_limits(purchasing_client):
    payload = supplier_payload(
        supplier_code="X" * 40,
        supplier_name="X" * 180,
        contact_name="X" * 120,
        phone="1" * 20,
        email="x" * 138 + "@example.com",
        tax_code="1" * 30,
        address="X" * 1000,
    )
    response = purchasing_client.post(SUPPLIERS, json=payload)
    assert response.status_code == 201, response.text
    for field, value in payload.items():
        assert response.json()["data"][field] == value


@pytest.mark.parametrize("field", ["supplier_code", "supplier_name"])
@pytest.mark.parametrize("value", ["", " \n\t ", None])
def test_supplier_create_requires_nonempty_code_and_name(purchasing_client, field, value):
    assert_error(purchasing_client.post(SUPPLIERS, json=supplier_payload(**{field: value})), 422)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("supplier_code", "X" * 41),
        ("supplier_name", "X" * 181),
        ("contact_name", "X" * 121),
        ("phone", "1" * 21),
        ("email", "x" * 140 + "@example.com"),
        ("tax_code", "1" * 31),
        ("email", "missing-at.example.com"),
        ("email", "a b@example.com"),
        ("status", "UNKNOWN"),
    ],
)
@pytest.mark.parametrize("method", ["post", "patch"])
def test_supplier_validates_lengths_email_and_status(purchasing_client, field, value, method):
    path = SUPPLIERS if method == "post" else f"{SUPPLIERS}/1"
    payload = supplier_payload(**{field: value}) if method == "post" else {field: value}
    assert_error(purchasing_client.request(method, path, json=payload), 422)


@pytest.mark.parametrize(
    ("field", "value"),
    [("supplier_id", 999), ("created_at", "2020-01-01"), ("updated_at", "2020-01-01")],
)
@pytest.mark.parametrize("method", ["post", "patch"])
def test_supplier_rejects_server_owned_fields(purchasing_client, field, value, method):
    path = SUPPLIERS if method == "post" else f"{SUPPLIERS}/1"
    payload = supplier_payload(**{field: value}) if method == "post" else {field: value}
    assert_error(purchasing_client.request(method, path, json=payload), 422)


def test_supplier_list_paginates_and_counts_all_matches(purchasing_client):
    response = purchasing_client.get(SUPPLIERS, params={"limit": 2, "offset": 1})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 4
    assert data["limit"] == 2 and data["offset"] == 1
    assert [row["supplier_id"] for row in data["items"]] == [2, 3]
    empty = purchasing_client.get(SUPPLIERS, params={"offset": 10}).json()["data"]
    assert empty["total"] == 4 and empty["items"] == []


@pytest.mark.parametrize(
    "search", ["beta", "Ingredients", "Contact BETA", "0900000002", "beta@example.com"]
)
def test_supplier_search_matches_each_supported_field(purchasing_client, search):
    response = purchasing_client.get(SUPPLIERS, params={"search": search})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert [row["supplier_id"] for row in data["items"]] == [2]


@pytest.mark.parametrize(
    ("params", "expected_ids"),
    [
        ({"status": "ACTIVE"}, [1, 2]),
        ({"status": "INACTIVE"}, [3]),
        ({"status": "SUSPENDED"}, [4]),
        ({"status": "ACTIVE", "search": "supplier"}, []),
    ],
)
def test_supplier_list_filters_status_and_combines_search(purchasing_client, params, expected_ids):
    response = purchasing_client.get(SUPPLIERS, params=params)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == len(expected_ids)
    assert [row["supplier_id"] for row in data["items"]] == expected_ids


def test_supplier_list_rejects_unknown_status(purchasing_client):
    assert_error(purchasing_client.get(SUPPLIERS, params={"status": "UNKNOWN"}), 422)


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
@pytest.mark.parametrize("path", [SUPPLIERS, MAPPINGS])
def test_purchasing_list_rejects_invalid_pagination(purchasing_client, path, params):
    assert_error(purchasing_client.get(path, params=params), 422)


@pytest.mark.parametrize("path", [SUPPLIERS, MAPPINGS])
@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_purchasing_missing_resource_returns_standard_404(purchasing_client, path, method):
    kwargs = {"json": {}} if method == "patch" else {}
    assert_error(purchasing_client.request(method, f"{path}/999", **kwargs), 404)


def test_supplier_detail_and_patch_preserve_server_fields(purchasing_client):
    before = purchasing_client.get(f"{SUPPLIERS}/1").json()["data"]
    response = purchasing_client.patch(
        f"{SUPPLIERS}/1",
        json={
            "supplier_code": " updated ",
            "supplier_name": " Updated Name ",
            "contact_name": None,
            "email": " updated@example.com ",
            "address": " Updated address ",
            "tax_code": "12345",
            "status": "SUSPENDED",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["supplier_code"] == "UPDATED"
    assert data["supplier_name"] == "Updated Name"
    assert data["email"] == "updated@example.com"
    assert data["address"] == "Updated address"
    assert data["tax_code"] == "12345"
    assert data["contact_name"] is None
    assert data["phone"] == before["phone"]
    assert data["status"] == "SUSPENDED"
    assert data["supplier_id"] == before["supplier_id"]
    assert data["created_at"] == before["created_at"]
    assert datetime.fromisoformat(data["updated_at"]).year > 2020
    stored = purchasing_client.get(f"{SUPPLIERS}/1").json()["data"]
    # SQLite drops timezone offsets on reload; PostgreSQL preserves timestamptz.
    assert datetime.fromisoformat(stored.pop("updated_at")).replace(tzinfo=UTC) == (
        datetime.fromisoformat(data.pop("updated_at")).replace(tzinfo=UTC)
    )
    assert stored == data


def test_supplier_patch_checks_duplicate_excluding_itself(purchasing_client):
    unchanged = purchasing_client.patch(f"{SUPPLIERS}/1", json={"supplier_code": " acme "})
    assert unchanged.status_code == 200
    assert_error(
        purchasing_client.patch(
            f"{SUPPLIERS}/1", json={"supplier_code": " beta ", "supplier_name": "Wrong"}
        ),
        409,
    )
    stored = purchasing_client.get(f"{SUPPLIERS}/1").json()["data"]
    assert stored["supplier_code"] == "ACME" and stored["supplier_name"] == "Acme Foods"


@pytest.mark.parametrize("field", ["supplier_code", "supplier_name", "status"])
def test_supplier_patch_rejects_null_required_fields(purchasing_client, field):
    assert_error(purchasing_client.patch(f"{SUPPLIERS}/1", json={field: None}), 422)


def test_supplier_delete_soft_deletes_all_own_mappings(
    purchasing_client, purchasing_session, purchasing_engine
):
    seed_mapping(purchasing_session, 1, is_preferred=True)
    seed_mapping(purchasing_session, 2, ingredient_id=2, is_preferred=True)
    seed_mapping(purchasing_session, 3, supplier_id=2)
    response = purchasing_client.delete(f"{SUPPLIERS}/1")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "INACTIVE"
    assert datetime.fromisoformat(response.json()["data"]["updated_at"]).year > 2020
    with Session(purchasing_engine) as verification:
        assert verification.get(Supplier, 1).status == "INACTIVE"
        assert len(list(verification.scalars(select(Supplier)))) == 4
        for mapping_id in (1, 2):
            mapping = verification.get(SupplierIngredient, mapping_id)
            assert mapping.is_active is False and mapping.is_preferred is False
        assert verification.get(SupplierIngredient, 3).is_active is True
        assert len(list(verification.scalars(select(SupplierIngredient)))) == 3
    assert purchasing_client.get(f"{SUPPLIERS}/1").status_code == 200
    assert purchasing_client.delete(f"{SUPPLIERS}/1").status_code == 200


def test_supplier_patch_inactive_cascades_and_reactivation_keeps_mappings_disabled(
    purchasing_client, purchasing_session
):
    seed_mapping(purchasing_session, is_preferred=True)
    response = purchasing_client.patch(f"{SUPPLIERS}/1", json={"status": "INACTIVE"})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "INACTIVE"
    mapping = purchasing_client.get(f"{MAPPINGS}/1").json()["data"]
    assert mapping["is_active"] is False and mapping["is_preferred"] is False
    reactivated = purchasing_client.patch(f"{SUPPLIERS}/1", json={"status": "ACTIVE"})
    assert reactivated.status_code == 200
    mapping = purchasing_client.get(f"{MAPPINGS}/1").json()["data"]
    assert mapping["is_active"] is False and mapping["is_preferred"] is False


def test_mapping_create_returns_related_summaries_and_exact_quantities(purchasing_client):
    response = purchasing_client.post(MAPPINGS, json=mapping_payload(is_preferred=True))
    assert response.status_code == 201, response.text
    assert response.json()["success"] is True
    data = response.json()["data"]
    assert data["supplier"]["supplier_code"] == "ACME"
    assert data["ingredient"]["ingredient_name"] == "Flour"
    assert data["purchase_unit"]["unit_code"] == "KG"
    assert data["supplier_sku"] == "BOT-MI-01"
    assert data["lead_time_days"] == 2
    assert Decimal(data["base_qty_per_purchase_unit"]) == Decimal("1000.000")
    assert Decimal(data["minimum_order_qty"]) == Decimal("5.000")
    assert Decimal(data["latest_unit_price"]) == Decimal("28000.00")
    assert data["is_preferred"] is True and data["is_active"] is True
    detail = purchasing_client.get(f"{MAPPINGS}/{data['supplier_ingredient_id']}")
    assert detail.status_code == 200 and detail.json()["data"] == data


def test_mapping_defaults_do_not_infer_packaging_or_price(purchasing_client):
    response = purchasing_client.post(
        MAPPINGS,
        json={
            "supplier_id": 1,
            "ingredient_id": 1,
            "purchase_unit_id": 3,
            "base_qty_per_purchase_unit": "12.500",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert Decimal(data["base_qty_per_purchase_unit"]) == Decimal("12.500")
    assert Decimal(data["minimum_order_qty"]) == Decimal("1.000")
    assert data["lead_time_days"] == 0
    assert data["supplier_sku"] is None and data["latest_unit_price"] is None
    assert data["is_active"] is True and data["is_preferred"] is False


@pytest.mark.parametrize("price", [None, "0.00"])
def test_mapping_allows_cross_dimension_purchase_unit_and_nullable_or_zero_price(
    purchasing_client, price
):
    response = purchasing_client.post(
        MAPPINGS,
        json=mapping_payload(
            purchase_unit_id=3,
            base_qty_per_purchase_unit="25000.000",
            latest_unit_price=price,
            supplier_sku="  ",
        ),
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["purchase_unit"]["dimension"] == "COUNT"
    assert Decimal(data["base_qty_per_purchase_unit"]) == Decimal("25000.000")
    assert data["supplier_sku"] is None
    if price is None:
        assert data["latest_unit_price"] is None
    else:
        assert Decimal(data["latest_unit_price"]) == Decimal("0.00")


@pytest.mark.parametrize(
    ("changes", "status_code"),
    [
        ({"supplier_id": 999}, 404),
        ({"supplier_id": 3}, 400),
        ({"supplier_id": 4}, 400),
        ({"ingredient_id": 999}, 404),
        ({"ingredient_id": 3}, 400),
        ({"purchase_unit_id": 999}, 404),
        ({"purchase_unit_id": 4}, 400),
    ],
)
def test_mapping_create_requires_existing_active_references(
    purchasing_client, changes, status_code
):
    assert_error(purchasing_client.post(MAPPINGS, json=mapping_payload(**changes)), status_code)


@pytest.mark.parametrize("active", [True, False])
def test_mapping_rejects_duplicate_pair_even_when_existing_mapping_is_inactive(
    purchasing_client, purchasing_session, active
):
    seed_mapping(purchasing_session, is_active=active)
    assert_error(purchasing_client.post(MAPPINGS, json=mapping_payload()), 409)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("base_qty_per_purchase_unit", "0"),
        ("base_qty_per_purchase_unit", "-0.001"),
        ("base_qty_per_purchase_unit", "1.0001"),
        ("base_qty_per_purchase_unit", "100000000000.000"),
        ("lead_time_days", -1),
        ("lead_time_days", 0.5),
        ("lead_time_days", 2147483648),
        ("minimum_order_qty", "0"),
        ("minimum_order_qty", "-0.001"),
        ("minimum_order_qty", "1.0001"),
        ("minimum_order_qty", "100000000000.000"),
        ("latest_unit_price", "-0.01"),
        ("latest_unit_price", "0.001"),
        ("latest_unit_price", "1000000000000.00"),
        ("latest_unit_price", "NaN"),
        ("base_qty_per_purchase_unit", "Infinity"),
        ("supplier_sku", "X" * 81),
    ],
)
@pytest.mark.parametrize("method", ["post", "patch"])
def test_mapping_validates_numeric_bounds_precision_and_sku(
    purchasing_client, purchasing_session, method, field, value
):
    if method == "patch":
        seed_mapping(purchasing_session)
    path = MAPPINGS if method == "post" else f"{MAPPINGS}/1"
    payload = mapping_payload(**{field: value}) if method == "post" else {field: value}
    assert_error(purchasing_client.request(method, path, json=payload), 422)


@pytest.mark.parametrize(
    "field",
    [
        "purchase_unit_id",
        "base_qty_per_purchase_unit",
        "lead_time_days",
        "minimum_order_qty",
        "is_preferred",
        "is_active",
    ],
)
def test_mapping_patch_rejects_null_for_required_fields(
    purchasing_client, purchasing_session, field
):
    seed_mapping(purchasing_session)
    assert_error(purchasing_client.patch(f"{MAPPINGS}/1", json={field: None}), 422)


@pytest.mark.parametrize("field", ["supplier_id", "ingredient_id", "supplier_ingredient_id"])
def test_mapping_patch_rejects_immutable_identifiers(purchasing_client, purchasing_session, field):
    seed_mapping(purchasing_session)
    assert_error(purchasing_client.patch(f"{MAPPINGS}/1", json={field: 2}), 422)


def test_mapping_create_rejects_client_owned_id(purchasing_client):
    assert_error(
        purchasing_client.post(MAPPINGS, json=mapping_payload(supplier_ingredient_id=999)), 422
    )


def test_mapping_patch_updates_purchase_details_and_clears_nullable_fields(
    purchasing_client, purchasing_session
):
    seed_mapping(purchasing_session)
    response = purchasing_client.patch(
        f"{MAPPINGS}/1",
        json={
            "supplier_sku": " ",
            "purchase_unit_id": 3,
            "base_qty_per_purchase_unit": "25000.125",
            "lead_time_days": 0,
            "minimum_order_qty": "0.001",
            "latest_unit_price": None,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["supplier_sku"] is None and data["latest_unit_price"] is None
    assert data["supplier_id"] == 1 and data["ingredient_id"] == 1
    assert data["purchase_unit"]["unit_code"] == "BOX"
    assert Decimal(data["base_qty_per_purchase_unit"]) == Decimal("25000.125")
    assert Decimal(data["minimum_order_qty"]) == Decimal("0.001")
    assert data["lead_time_days"] == 0


@pytest.mark.parametrize(("unit_id", "status_code"), [(999, 404), (4, 400)])
def test_mapping_patch_validates_replacement_purchase_unit(
    purchasing_client, purchasing_session, unit_id, status_code
):
    seed_mapping(purchasing_session)
    assert_error(
        purchasing_client.patch(f"{MAPPINGS}/1", json={"purchase_unit_id": unit_id}),
        status_code,
    )


@pytest.mark.parametrize("reference", ["supplier", "ingredient", "purchase_unit"])
@pytest.mark.parametrize("active", [True, False])
def test_mapping_active_patch_and_reactivation_require_active_references(
    purchasing_client, purchasing_session, reference, active
):
    seed_mapping(purchasing_session, is_active=active)
    if reference == "supplier":
        purchasing_session.get(Supplier, 1).status = "SUSPENDED"
    elif reference == "ingredient":
        purchasing_session.get(Ingredient, 1).status = "INACTIVE"
    else:
        purchasing_session.get(Unit, 2).is_active = False
    purchasing_session.commit()
    assert_error(purchasing_client.patch(f"{MAPPINGS}/1", json={"is_active": True}), 400)
    purchasing_session.expire_all()
    assert purchasing_session.get(SupplierIngredient, 1).is_active is active


def test_mapping_inactive_can_be_edited_and_disabled_after_supplier_is_inactive(
    purchasing_client, purchasing_session
):
    seed_mapping(purchasing_session)
    purchasing_session.get(Supplier, 1).status = "INACTIVE"
    purchasing_session.commit()
    disabled = purchasing_client.patch(f"{MAPPINGS}/1", json={"is_active": False})
    assert disabled.status_code == 200, disabled.text
    edited = purchasing_client.patch(f"{MAPPINGS}/1", json={"supplier_sku": "Archived"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["data"]["supplier_sku"] == "Archived"
    assert edited.json()["data"]["is_active"] is False


def test_mapping_create_preferred_replaces_previous_for_same_ingredient_only(
    purchasing_client, purchasing_session, purchasing_engine
):
    seed_mapping(purchasing_session, 1, is_preferred=True)
    seed_mapping(purchasing_session, 2, ingredient_id=2, is_preferred=True)
    response = purchasing_client.post(
        MAPPINGS, json=mapping_payload(supplier_id=2, is_preferred=True)
    )
    assert response.status_code == 201, response.text
    new_id = response.json()["data"]["supplier_ingredient_id"]
    with Session(purchasing_engine) as verification:
        previous = verification.get(SupplierIngredient, 1)
        assert previous.is_preferred is False and previous.is_active is True
        assert verification.get(SupplierIngredient, 2).is_preferred is True
        assert verification.get(SupplierIngredient, new_id).is_preferred is True


def test_mapping_patch_flushes_old_preferred_before_lower_id_target(
    purchasing_client, purchasing_session, purchasing_engine
):
    # A single flush updates by primary key and violates the partial unique
    # index if mapping 1 becomes preferred while mapping 2 is still preferred.
    seed_mapping(purchasing_session, 1)
    seed_mapping(purchasing_session, 2, supplier_id=2, is_preferred=True)
    response = purchasing_client.patch(f"{MAPPINGS}/1", json={"is_preferred": True})
    assert response.status_code == 200, response.text
    with Session(purchasing_engine) as verification:
        assert verification.get(SupplierIngredient, 1).is_preferred is True
        assert verification.get(SupplierIngredient, 2).is_preferred is False
    repeated = purchasing_client.patch(f"{MAPPINGS}/1", json={"is_preferred": True})
    assert repeated.status_code == 200


@pytest.mark.parametrize("method", ["post", "patch"])
def test_mapping_inactive_never_keeps_preferred(purchasing_client, purchasing_session, method):
    seed_mapping(purchasing_session, 1, is_preferred=True)
    if method == "post":
        response = purchasing_client.post(
            MAPPINGS,
            json=mapping_payload(supplier_id=2, is_active=False, is_preferred=True),
        )
        assert response.status_code == 201, response.text
        assert purchasing_client.get(f"{MAPPINGS}/1").json()["data"]["is_preferred"] is True
    else:
        response = purchasing_client.patch(
            f"{MAPPINGS}/1", json={"is_active": False, "is_preferred": True}
        )
        assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["is_active"] is False and data["is_preferred"] is False
    repeated = purchasing_client.patch(
        f"{MAPPINGS}/{data['supplier_ingredient_id']}", json={"is_preferred": True}
    )
    assert repeated.status_code == 200
    assert repeated.json()["data"]["is_preferred"] is False


def test_mapping_deactivation_automatically_clears_preferred(purchasing_client, purchasing_session):
    seed_mapping(purchasing_session, is_preferred=True)
    response = purchasing_client.patch(f"{MAPPINGS}/1", json={"is_active": False})
    assert response.status_code == 200
    assert response.json()["data"]["is_preferred"] is False


def test_mapping_delete_preserves_row_and_clears_flags(
    purchasing_client, purchasing_session, purchasing_engine
):
    seed_mapping(purchasing_session, is_preferred=True)
    response = purchasing_client.delete(f"{MAPPINGS}/1")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["is_active"] is False and data["is_preferred"] is False
    with Session(purchasing_engine) as verification:
        mapping = verification.get(SupplierIngredient, 1)
        assert mapping is not None
        assert mapping.is_active is False and mapping.is_preferred is False
    assert purchasing_client.get(f"{MAPPINGS}/1").status_code == 200
    assert purchasing_client.delete(f"{MAPPINGS}/1").status_code == 200


@pytest.mark.parametrize(
    ("params", "expected_ids"),
    [
        ({"supplier_id": 1}, [1, 2]),
        ({"ingredient_id": 1}, [1, 3]),
        ({"is_active": True}, [1, 3]),
        ({"is_active": False}, [2]),
        ({"is_preferred": True}, [1]),
        ({"is_preferred": False}, [2, 3]),
        ({"supplier_id": 1, "ingredient_id": 1, "is_active": True, "is_preferred": True}, [1]),
        ({"supplier_id": 999}, []),
    ],
)
def test_mapping_list_filters(purchasing_client, purchasing_session, params, expected_ids):
    seed_mapping(purchasing_session, 1, is_preferred=True)
    seed_mapping(purchasing_session, 2, ingredient_id=2, is_active=False)
    seed_mapping(purchasing_session, 3, supplier_id=2)
    response = purchasing_client.get(MAPPINGS, params=params)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == len(expected_ids)
    assert [row["supplier_ingredient_id"] for row in data["items"]] == expected_ids


def test_mapping_list_paginates_and_eager_loads_summaries_without_n_plus_one(
    purchasing_client, purchasing_session, purchasing_engine
):
    seed_mapping(purchasing_session, 1)
    seed_mapping(purchasing_session, 2, ingredient_id=2, purchase_unit_id=3)
    seed_mapping(purchasing_session, 3, supplier_id=2)
    seed_mapping(purchasing_session, 4, supplier_id=2, ingredient_id=2)
    purchasing_session.expunge_all()
    queries = []

    def record_select(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    event.listen(purchasing_engine, "before_cursor_execute", record_select)
    try:
        response = purchasing_client.get(MAPPINGS, params={"limit": 3, "offset": 1})
    finally:
        event.remove(purchasing_engine, "before_cursor_execute", record_select)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 4 and data["limit"] == 3 and data["offset"] == 1
    assert [row["supplier_ingredient_id"] for row in data["items"]] == [2, 3, 4]
    for row in data["items"]:
        assert row["supplier"]["supplier_id"] == row["supplier_id"]
        assert row["supplier"]["supplier_name"]
        assert row["ingredient"]["ingredient_id"] == row["ingredient_id"]
        assert row["ingredient"]["ingredient_name"]
        assert row["purchase_unit"]["unit_id"] == row["purchase_unit_id"]
        assert row["purchase_unit"]["unit_name"]
    assert len(queries) <= 2, queries
    empty = purchasing_client.get(MAPPINGS, params={"offset": 10}).json()["data"]
    assert empty["total"] == 4 and empty["items"] == []


@pytest.mark.parametrize("method", ["post", "patch"])
@pytest.mark.parametrize("failure_point", ["preferred_flush", "commit"])
def test_preferred_change_rolls_back_all_rows_on_database_failure(
    purchasing_client, purchasing_session, purchasing_engine, monkeypatch, method, failure_point
):
    seed_mapping(purchasing_session, 1, is_preferred=True)
    if method == "patch":
        seed_mapping(purchasing_session, 2, supplier_id=2)
    real_flush = purchasing_session.flush
    failures = []

    def fail_preferred_flush(*args, **kwargs):
        preferred_target = any(
            isinstance(entity, SupplierIngredient)
            and entity.supplier_id == 2
            and entity.is_preferred
            for entity in list(purchasing_session.new) + list(purchasing_session.dirty)
        )
        real_flush(*args, **kwargs)
        if preferred_target:
            failures.append(True)
            raise integrity_failure()

    def fail_commit():
        failures.append(True)
        raise integrity_failure()

    path = MAPPINGS if method == "post" else f"{MAPPINGS}/2"
    payload = (
        mapping_payload(supplier_id=2, is_preferred=True)
        if method == "post"
        else {"is_preferred": True, "supplier_sku": "Uncommitted"}
    )
    with monkeypatch.context() as patch:
        if failure_point == "preferred_flush":
            patch.setattr(purchasing_session, "flush", fail_preferred_flush)
        else:
            patch.setattr(purchasing_session, "commit", fail_commit)
        response = purchasing_client.request(method, path, json=payload)
    assert_error(response, 409)
    assert failures
    assert not purchasing_session.in_transaction()
    with Session(purchasing_engine) as verification:
        old = verification.get(SupplierIngredient, 1)
        assert old.is_active is True and old.is_preferred is True
        replacement = verification.get(SupplierIngredient, 2)
        if method == "post":
            assert replacement is None
        else:
            assert replacement.is_preferred is False
            assert replacement.supplier_sku == "BOT-MI-01"
    retry = purchasing_client.request(method, path, json=payload)
    assert retry.status_code == (201 if method == "post" else 200), retry.text


@pytest.mark.parametrize("path", [SUPPLIERS, MAPPINGS])
@pytest.mark.parametrize("method", ["delete", "patch"])
def test_soft_delete_rolls_back_supplier_and_mapping_changes_on_commit_failure(
    purchasing_client, purchasing_session, purchasing_engine, monkeypatch, path, method
):
    seed_mapping(purchasing_session, 1, is_preferred=True)
    seed_mapping(purchasing_session, 2, ingredient_id=2, is_preferred=True)

    def fail_commit():
        raise integrity_failure()

    with monkeypatch.context() as patch:
        patch.setattr(purchasing_session, "commit", fail_commit)
        if method == "patch":
            payload = {"status": "INACTIVE"} if path == SUPPLIERS else {"is_active": False}
            response = purchasing_client.patch(f"{path}/1", json=payload)
        else:
            response = purchasing_client.delete(f"{path}/1")
    assert_error(response, 409)
    assert not purchasing_session.in_transaction()
    with Session(purchasing_engine) as verification:
        supplier = verification.get(Supplier, 1)
        assert supplier.status == "ACTIVE"
        assert supplier.updated_at.year == 2020
        for mapping_id in (1, 2):
            mapping = verification.get(SupplierIngredient, mapping_id)
            assert mapping.is_active is True and mapping.is_preferred is True


@pytest.mark.parametrize("failure_point", ["flush", "commit"])
def test_supplier_create_rolls_back_and_sanitizes_integrity_errors(
    purchasing_client, purchasing_session, purchasing_engine, monkeypatch, failure_point
):
    def fail(*args, **kwargs):
        raise integrity_failure()

    with monkeypatch.context() as patch:
        patch.setattr(purchasing_session, failure_point, fail)
        response = purchasing_client.post(SUPPLIERS, json=supplier_payload())
    assert_error(response, 409)
    assert not purchasing_session.in_transaction()
    with Session(purchasing_engine) as verification:
        assert len(list(verification.scalars(select(Supplier)))) == 4


@pytest.mark.parametrize("method", ["post", "patch"])
def test_preferred_mutations_lock_parent_then_ingredient_then_ordered_mappings(
    purchasing_client, purchasing_session, method
):
    seed_mapping(purchasing_session, 1, is_preferred=True)
    if method == "patch":
        seed_mapping(purchasing_session, 2, supplier_id=2)
    locks = []

    def record_lock(orm_execute_state):
        statement = orm_execute_state.statement
        if getattr(statement, "_for_update_arg", None) is not None:
            locks.append(str(statement.compile(dialect=postgresql.dialect())))

    event.listen(purchasing_session, "do_orm_execute", record_lock)
    try:
        response = (
            purchasing_client.post(MAPPINGS, json=mapping_payload(supplier_id=2, is_preferred=True))
            if method == "post"
            else purchasing_client.patch(f"{MAPPINGS}/2", json={"is_preferred": True})
        )
    finally:
        event.remove(purchasing_session, "do_orm_execute", record_lock)
    assert response.status_code == (201 if method == "post" else 200), response.text
    assert "FROM restaurant_ai.suppliers" in locks[0]
    assert "FROM restaurant_ai.ingredients" in locks[1]
    mapping_locks = [sql for sql in locks if "FROM restaurant_ai.supplier_ingredients" in sql]
    assert mapping_locks
    assert any(
        "supplier_ingredients.ingredient_id =" in sql
        and "ORDER BY restaurant_ai.supplier_ingredients.supplier_ingredient_id" in sql
        and "FOR UPDATE" in sql
        for sql in mapping_locks
    )


def test_first_preferred_mapping_locks_ingredient_even_without_existing_mappings(
    purchasing_client, purchasing_session
):
    locks = []

    def record_lock(orm_execute_state):
        statement = orm_execute_state.statement
        if getattr(statement, "_for_update_arg", None) is not None:
            locks.append(str(statement.compile(dialect=postgresql.dialect())))

    event.listen(purchasing_session, "do_orm_execute", record_lock)
    try:
        response = purchasing_client.post(MAPPINGS, json=mapping_payload(is_preferred=True))
    finally:
        event.remove(purchasing_session, "do_orm_execute", record_lock)
    assert response.status_code == 201, response.text
    assert any("FROM restaurant_ai.ingredients" in sql and "FOR UPDATE" in sql for sql in locks)


@pytest.mark.parametrize("path", [SUPPLIERS, MAPPINGS])
@pytest.mark.parametrize("detail", [False, True])
def test_database_read_failures_are_sanitized_even_in_debug_mode(
    purchasing_client, purchasing_session, monkeypatch, path, detail
):
    purchasing_client.app.debug = True

    def fail_query(*args, **kwargs):
        raise OperationalError("private SQL", {}, Exception("private connection string"))

    with monkeypatch.context() as patch:
        patch.setattr(purchasing_session, "execute", fail_query)
        patch.setattr(purchasing_session, "scalar", fail_query)
        response = purchasing_client.get(f"{path}/1" if detail else path)
    assert_error(response, 503)
    assert not purchasing_session.in_transaction()
