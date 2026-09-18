import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from pydantic import SecretStr
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.models.rbac import AuditLog, Role, RolePermission, User, UserRole
from app.modules.inventory_auth.security import AUDIENCE, ISSUER, signing_key
from tests.inventory_auth_fixtures import TEST_PASSWORD, authenticate_client
from tests.test_stock import seed_lot

AUTH = "/api/v1/inventory-auth"


def login(client, username="manager", password=TEST_PASSWORD):
    return client.post(f"{AUTH}/login", json={"username": username, "password": password})


def test_login_me_and_stateless_logout(stock_client, stock_session):
    data = authenticate_client(stock_client)
    claims = jwt.decode(
        data["access_token"],
        signing_key(get_settings()),
        algorithms=["HS256"],
        audience=AUDIENCE,
        issuer=ISSUER,
    )
    assert set(claims) == {"sub", "aud", "iss", "iat", "exp", "jti"}
    assert claims["sub"] == "1" and claims["exp"] - claims["iat"] == 480 * 60
    response = stock_client.get(f"{AUTH}/me")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    user = response.json()["data"]["user"]
    assert user["user_id"] == 1 and user["roles"][0]["role_code"] == "MANAGER"
    assert "PURCHASE_APPROVE" in user["permissions"]
    assert "password" not in response.text and "access_token" not in response.text
    assert stock_client.post(f"{AUTH}/logout").json()["data"] == {"stateless": True}
    assert stock_client.get(f"{AUTH}/me").status_code == 200
    audit = list(stock_session.scalars(select(AuditLog)))
    assert {row.action_code for row in audit} == {"INVENTORY_LOGIN", "INVENTORY_LOGOUT"}
    assert all(row.actor_user_id == 1 for row in audit)
    assert stock_session.get(User, 1).last_login_at is not None


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("manager", "wrong"),
        ("missing", TEST_PASSWORD),
        ("locked", TEST_PASSWORD),
        ("manager", "x" * 73),
    ],
)
def test_invalid_credentials_are_indistinguishable(stock_client, username, password):
    response = login(stock_client, username, password)
    assert response.status_code == 401
    assert response.json()["message"] == "Invalid username or password"


def test_sales_report_permission_does_not_grant_inventory_access(stock_client):
    assert login(stock_client, "sales").status_code == 403


@pytest.mark.parametrize(
    "path",
    [
        "/inventory/units",
        "/inventory/ingredients",
        "/inventory/stock",
        "/inventory/stock-lots",
        "/inventory/stock-movements",
        "/inventory/stocktakes",
        "/purchasing/suppliers",
        "/purchasing/supplier-ingredients",
        "/purchasing/purchase-orders",
        "/purchasing/goods-receipts",
        "/recipes",
        "/inventory-auth/me",
        "/inventory-auth/logout",
    ],
)
def test_all_router_groups_require_bearer(stock_client, path):
    stock_client.headers.pop("Authorization")
    method = stock_client.post if path.endswith("logout") else stock_client.get
    assert method(f"/api/v1{path}").status_code == 401


@pytest.mark.parametrize(
    "change",
    [
        "expired",
        "audience",
        "issuer",
        "signature",
        "algorithm",
        "missing_jti",
        "bad_subject",
        "future_iat",
    ],
)
def test_invalid_tokens_are_rejected(stock_client, change):
    now = datetime.now(UTC)
    payload = {
        "sub": "1",
        "aud": AUDIENCE,
        "iss": ISSUER,
        "iat": now,
        "exp": now + timedelta(minutes=1),
        "jti": str(uuid4()),
    }
    key = signing_key(get_settings())
    algorithm = "HS256"
    if change == "expired":
        payload["exp"] = now - timedelta(seconds=2)
    if change == "audience":
        payload["aud"] = "sales"
    if change == "issuer":
        payload["iss"] = "sales-auth"
    if change == "signature":
        key = "another-independent-signing-key-123456789"
    if change == "algorithm":
        algorithm = "HS384"
    if change == "missing_jti":
        del payload["jti"]
    if change == "bad_subject":
        payload["sub"] = "not-an-id"
    if change == "future_iat":
        payload["iat"] = now + timedelta(hours=1)
    stock_client.headers["Authorization"] = (
        f"Bearer {jwt.encode(payload, key, algorithm=algorithm)}"
    )
    assert stock_client.get(f"{AUTH}/me").status_code == 401


def test_inventory_jwt_is_invalid_for_a_sales_audience(stock_client):
    token = authenticate_client(stock_client)["access_token"]
    # Sales has no JWT dependency yet. Verify cryptographic separation without modifying Sales.
    with pytest.raises(jwt.InvalidAudienceError):
        jwt.decode(token, signing_key(get_settings()), algorithms=["HS256"], audience="sales")


@pytest.mark.parametrize("status", ["LOCKED", "INACTIVE"])
def test_disabling_user_invalidates_next_request(stock_client, stock_session, status):
    stock_session.get(User, 1).status = status
    stock_session.commit()
    assert stock_client.get("/api/v1/inventory/units").status_code == 401


@pytest.mark.parametrize("revocation", ["permission", "role", "assignment"])
def test_revocation_is_reloaded_from_database(stock_client, stock_session, revocation):
    if revocation == "permission":
        stock_session.execute(delete(RolePermission).where(RolePermission.role_id == 1))
    if revocation == "role":
        stock_session.get(Role, 1).is_active = False
    if revocation == "assignment":
        stock_session.execute(delete(UserRole).where(UserRole.user_id == 1))
    stock_session.commit()
    assert stock_client.get("/api/v1/inventory/units").status_code == 403
    assert stock_client.get(f"{AUTH}/me").json()["data"]["user"]["permissions"] == []


def test_warehouse_can_issue_but_cannot_approve_or_edit_suppliers(stock_client, stock_session):
    authenticate_client(stock_client, "warehouse")
    assert stock_client.get("/api/v1/inventory/stock").status_code == 200
    assert (
        stock_client.post(
            "/api/v1/purchasing/purchase-orders/1/status",
            json={"status": "APPROVED", "actor_id": 1},
        ).status_code
        == 403
    )
    assert stock_client.post("/api/v1/purchasing/suppliers", json={}).status_code == 403
    seed_lot(stock_session)
    result = stock_client.post(
        "/api/v1/inventory/stock/issues",
        json={
            "ingredient_id": 1,
            "quantity": "1",
            "unit_id": 1,
            "performed_by": 1,
            "reason": "Spoof attempt",
        },
    )
    assert result.status_code == 201, result.text
    assert all(row["performed_by"] == 2 for row in result.json()["data"]["movements"])
    result = stock_client.post(
        "/api/v1/inventory/stock-lots/1/adjust",
        json={"actual_quantity": "98", "performed_by": 1, "reason": "Spoof attempt"},
    )
    assert result.status_code == 200, result.text
    assert all(row["performed_by"] == 2 for row in result.json()["data"]["movements"])


def test_purchaser_permissions_and_actor(stock_client):
    authenticate_client(stock_client, "purchaser")
    assert stock_client.get("/api/v1/purchasing/suppliers").status_code == 200
    for path in ["/inventory/stock/issues", "/inventory/stocktakes", "/purchasing/goods-receipts"]:
        assert stock_client.post("/api/v1" + path, json={}).status_code == 403
    result = stock_client.post(
        "/api/v1/purchasing/purchase-orders",
        json={
            "supplier_id": 1,
            "created_by": 1,
            "items": [
                {"supplier_ingredient_id": 1, "ordered_quantity": "1", "expected_unit_price": "10"}
            ],
        },
    )
    assert result.status_code == 201, result.text
    assert result.json()["data"]["created_by"] == 3
    order_id = result.json()["data"]["purchase_order_id"]
    result = stock_client.post(
        f"/api/v1/purchasing/purchase-orders/{order_id}/status",
        json={"status": "APPROVED", "actor_id": 1},
    )
    assert result.status_code == 403


@pytest.mark.parametrize("configuration", ["missing", "short", "reused", "algorithm"])
def test_missing_or_reused_secret_fails_closed(stock_client, monkeypatch, configuration):
    settings = get_settings()
    if configuration == "missing":
        monkeypatch.setattr(settings, "inventory_jwt_secret_key", None)
    elif configuration == "short":
        monkeypatch.setattr(settings, "inventory_jwt_secret_key", SecretStr("short"))
    elif configuration == "reused":
        monkeypatch.setattr(
            settings, "jwt_secret_key", settings.inventory_jwt_secret_key.get_secret_value()
        )
    else:
        monkeypatch.setattr(settings, "inventory_jwt_algorithm", "none")
    assert stock_client.get(f"{AUTH}/status").json()["data"] == {
        "implemented": True,
        "configured": False,
    }
    assert login(stock_client).status_code == 503


def test_all_business_routes_enforce_auth_before_request_validation(stock_client):
    stock_client.headers.pop("Authorization")
    checked = 0
    for template, operations in stock_client.app.openapi()["paths"].items():
        if not template.startswith(
            ("/api/v1/inventory/", "/api/v1/purchasing/", "/api/v1/recipes")
        ):
            continue
        path = re.sub(r"\{[^}]+\}", "1", template)
        for method in operations:
            checked += 1
            result = stock_client.request(method, path, json={} if method != "get" else None)
            assert result.status_code == 401, (method, path, result.text)
    assert checked >= 40


def test_server_owns_receipt_approval_and_stocktake_actors(stock_client):
    prefix = "/api/v1"
    order = stock_client.post(
        prefix + "/purchasing/purchase-orders",
        json={
            "supplier_id": 1,
            "created_by": 2,
            "items": [
                {"supplier_ingredient_id": 1, "ordered_quantity": "1", "expected_unit_price": "10"}
            ],
        },
    ).json()["data"]
    assert order["created_by"] == 1
    for status in ("PENDING_APPROVAL", "APPROVED", "ORDERED"):
        result = stock_client.post(
            f"{prefix}/purchasing/purchase-orders/{order['purchase_order_id']}/status",
            json={"status": status, "actor_id": 2},
        )
        assert result.status_code == 200, result.text
        if status == "APPROVED":
            assert result.json()["data"]["approved_by"] == 1
    authenticate_client(stock_client, "warehouse")
    result = stock_client.post(
        prefix + "/purchasing/goods-receipts",
        json={
            "purchase_order_id": order["purchase_order_id"],
            "received_by": 1,
            "items": [
                {
                    "purchase_order_item_id": order["items"][0]["purchase_order_item_id"],
                    "received_quantity": "1",
                    "actual_unit_price": "10",
                    "lot_code": "AUTH-LOT",
                }
            ],
        },
    )
    assert result.status_code == 201, result.text
    receipt = result.json()["data"]
    assert receipt["received_by"] == 2
    authenticate_client(stock_client)
    assert (
        stock_client.post(
            f"{prefix}/purchasing/goods-receipts/{receipt['goods_receipt_id']}/confirm"
        ).status_code
        == 200
    )
    movements = stock_client.get(prefix + "/inventory/stock-movements").json()["data"]["items"]
    assert all(row["performed_by"] == 1 for row in movements)
    lot_id = stock_client.get(prefix + "/inventory/stock-lots").json()["data"]["items"][0][
        "stock_lot_id"
    ]
    authenticate_client(stock_client, "warehouse")
    result = stock_client.post(prefix + "/inventory/stocktakes", json={"created_by": 1})
    assert result.status_code == 201
    stocktake = result.json()["data"]
    assert stocktake["created_by"] == 2
    url = f"{prefix}/inventory/stocktakes/{stocktake['stocktake_id']}"
    started = stock_client.post(url + "/start", json={"stock_lot_ids": [lot_id]}).json()["data"]
    item_id = started["items"][0]["stocktake_item_id"]
    assert (
        stock_client.patch(
            f"{url}/items/{item_id}",
            json={"actual_quantity": "999", "adjustment_reason": "Authenticated count"},
        ).status_code
        == 200
    )
    result = stock_client.post(url + "/complete", json={"completed_by": 1})
    assert result.status_code == 200, result.text
    assert result.json()["data"]["completed_by"] == 2
    movements = stock_client.get(prefix + "/inventory/stock-movements").json()["data"]["items"]
    assert [row["performed_by"] for row in movements if row["stocktake_item_id"]] == [2]


def test_admin_role_name_does_not_bypass_revoked_permissions(stock_client, stock_session):
    stock_session.get(Role, 1).role_code = "ADMIN"
    stock_session.execute(delete(RolePermission).where(RolePermission.role_id == 1))
    stock_session.commit()
    assert login(stock_client).status_code == 403
