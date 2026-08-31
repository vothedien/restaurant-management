from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE', 'LOCKED')", name="ck_users_status"),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(150), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'ACTIVE'"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    roles: Mapped[list[UserRole]] = relationship("UserRole", foreign_keys="UserRole.user_id")
    assigned_roles: Mapped[list[UserRole]] = relationship(
        "UserRole", foreign_keys="UserRole.assigned_by"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        "AuditLog", foreign_keys="AuditLog.actor_user_id"
    )


class Role(Base):
    __tablename__ = "roles"

    role_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    role_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    role_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    users: Mapped[list[UserRole]] = relationship("UserRole", back_populates="role")
    permissions: Mapped[list[RolePermission]] = relationship(
        "RolePermission", back_populates="role"
    )


class Permission(Base):
    __tablename__ = "permissions"

    permission_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    permission_code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    permission_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    roles: Mapped[list[RolePermission]] = relationship(
        "RolePermission", back_populates="permission"
    )


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.users.user_id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.roles.role_id", ondelete="CASCADE"), primary_key=True
    )
    assigned_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.users.user_id", ondelete="SET NULL")
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    user: Mapped[User] = relationship("User", foreign_keys=[user_id], back_populates="roles")
    role: Mapped[Role] = relationship("Role", back_populates="users")
    assigned_by_user: Mapped[User | None] = relationship("User", foreign_keys=[assigned_by])


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.roles.role_id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.permissions.permission_id", ondelete="CASCADE"),
        primary_key=True,
    )

    role: Mapped[Role] = relationship("Role", back_populates="permissions")
    permission: Mapped[Permission] = relationship("Permission", back_populates="roles")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(
            "old_values IS NULL OR jsonb_typeof(old_values) = 'object'",
            name="ck_audit_logs_old_values_object",
        ),
        CheckConstraint(
            "new_values IS NULL OR jsonb_typeof(new_values) = 'object'",
            name="ck_audit_logs_new_values_object",
        ),
    )

    audit_log_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.users.user_id", ondelete="SET NULL")
    )
    action_code: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    old_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(INET)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    actor: Mapped[User | None] = relationship(
        "User", foreign_keys=[actor_user_id], back_populates="audit_logs"
    )
