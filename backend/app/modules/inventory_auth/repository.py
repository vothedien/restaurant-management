from ipaddress import ip_address

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.rbac import AuditLog, Permission, Role, RolePermission, User, UserRole
from app.modules.inventory_auth.schemas import InventoryRole, InventoryUser


class InventoryAuthRepository:
    def by_username(self, session: Session, username: str) -> User | None:
        return session.scalar(
            select(User).where(User.username == username).execution_options(populate_existing=True)
        )

    def by_id(self, session: Session, user_id: int) -> User | None:
        return session.get(User, user_id, populate_existing=True)

    def principal(self, session: Session, user: User) -> InventoryUser:
        roles = list(
            session.scalars(
                select(Role)
                .join(UserRole, UserRole.role_id == Role.role_id)
                .where(UserRole.user_id == user.user_id, Role.is_active.is_(True))
                .order_by(Role.role_code)
            )
        )
        permissions = list(
            session.scalars(
                select(Permission.permission_code)
                .join(RolePermission, RolePermission.permission_id == Permission.permission_id)
                .where(RolePermission.role_id.in_([role.role_id for role in roles]))
                .distinct()
                .order_by(Permission.permission_code)
            )
        )
        return InventoryUser(
            user_id=user.user_id,
            username=user.username,
            full_name=user.full_name,
            roles=[
                InventoryRole(role_code=role.role_code, role_name=role.role_name) for role in roles
            ],
            permissions=permissions,
        )

    def audit(self, session: Session, user_id: int, action: str, client_host: str | None) -> None:
        try:
            address = str(ip_address(client_host)) if client_host else None
        except ValueError:
            address = None
        session.add(
            AuditLog(
                actor_user_id=user_id,
                action_code=action,
                entity_type="inventory_session",
                entity_id=str(user_id),
                description="Inventory authentication",
                old_values={},
                new_values={"audience": "inventory"},
                ip_address=address,
            )
        )
