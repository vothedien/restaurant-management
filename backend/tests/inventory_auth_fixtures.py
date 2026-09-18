"""Disposable RBAC fixtures; never used to provision production users."""

from functools import lru_cache

import bcrypt
from sqlalchemy import JSON, BigInteger, CheckConstraint, Integer, String
from sqlalchemy.dialects.postgresql import INET, JSONB

from app.db.models.rbac import AuditLog, Permission, Role, RolePermission, User, UserRole
from app.modules.inventory_auth.schemas import InventoryUser

TEST_PASSWORD = "inventory-test-only-password"
PERMISSIONS = (
    "INVENTORY_MANAGE",
    "PURCHASE_MANAGE",
    "PURCHASE_APPROVE",
    "RECIPE_MANAGE",
    "REPORT_VIEW",
    "ORDER_CREATE",
)


@lru_cache(maxsize=1)
def password_hash():
    return bcrypt.hashpw(TEST_PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode()


def add_rbac_tables(metadata):
    for model in (User, Role, Permission, UserRole, RolePermission, AuditLog):
        if model.__table__.key in metadata.tables:
            continue
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            if column.primary_key and isinstance(column.type, BigInteger):
                column.type = Integer()
            elif isinstance(column.type, JSONB):
                column.type = JSON()
            elif isinstance(column.type, INET):
                column.type = String()
        # Only the SQLite clone lacks PostgreSQL jsonb_typeof / INET types.
        for constraint in list(table.constraints):
            if isinstance(constraint, CheckConstraint) and "jsonb_typeof" in str(
                constraint.sqltext
            ):
                table.constraints.remove(constraint)


def seed_inventory_users(session):
    for index, code in enumerate(PERMISSIONS, 1):
        session.add(Permission(permission_id=index, permission_code=code, permission_name=code))
    session.flush()
    profiles = (
        (1, "manager", "MANAGER", "Quản lý kiểm thử", PERMISSIONS[:-1], "ACTIVE"),
        (2, "warehouse", "WAREHOUSE", "Nhân viên kho kiểm thử", ("INVENTORY_MANAGE",), "ACTIVE"),
        (
            3,
            "purchaser",
            "PURCHASER_TEST",
            "Nhân viên mua hàng kiểm thử",
            ("PURCHASE_MANAGE",),
            "ACTIVE",
        ),
        (4, "sales", "CASHIER", "Thu ngân kiểm thử", ("ORDER_CREATE", "REPORT_VIEW"), "ACTIVE"),
        (5, "locked", "LOCKED_TEST", "Tài khoản khóa kiểm thử", ("INVENTORY_MANAGE",), "LOCKED"),
    )
    for user_id, username, code, name, rights, status in profiles:
        user = session.get(User, user_id)
        if user is None:
            user = User(
                user_id=user_id,
                username=username,
                full_name=name,
                password_hash=password_hash(),
                status=status,
            )
            session.add(user)
        else:
            user.username, user.full_name, user.password_hash, user.status = (
                username,
                name,
                password_hash(),
                status,
            )
        session.add(Role(role_id=user_id, role_code=code, role_name=name, is_active=True))
        session.flush()
        session.add(UserRole(user_id=user_id, role_id=user_id))
        for right in rights:
            session.add(RolePermission(role_id=user_id, permission_id=PERMISSIONS.index(right) + 1))
    session.commit()


def unit_test_principal():
    """Dependency override only for pre-existing isolated service/serialization tests."""
    return InventoryUser(
        user_id=1,
        username="unit-test",
        full_name="Unit test user",
        roles=[],
        permissions=list(PERMISSIONS),
    )


def authenticate_client(client, username="manager"):
    response = client.post(
        "/api/v1/inventory-auth/login", json={"username": username, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, response.text
    client.headers["Authorization"] = f"Bearer {response.json()['data']['access_token']}"
    return response.json()["data"]
