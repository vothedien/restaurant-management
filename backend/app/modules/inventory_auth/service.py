from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.inventory_auth.repository import InventoryAuthRepository
from app.modules.inventory_auth.schemas import InventoryUser, LoginData, LoginRequest
from app.modules.inventory_auth.security import issue_token, signing_key, verify_password

# REPORT_VIEW alone is also assigned to Sales cashiers in the existing DDL.
ACCESS_PERMISSIONS = frozenset(
    {"INVENTORY_MANAGE", "PURCHASE_MANAGE", "PURCHASE_APPROVE", "RECIPE_MANAGE"}
)
STOCK_READ_PERMISSIONS = ("INVENTORY_MANAGE", "PURCHASE_MANAGE", "PURCHASE_APPROVE", "REPORT_VIEW")
PURCHASE_READ_PERMISSIONS = ("INVENTORY_MANAGE", "PURCHASE_MANAGE", "PURCHASE_APPROVE")


def check_access(user: InventoryUser) -> InventoryUser:
    if not ACCESS_PERMISSIONS.intersection(user.permissions):
        raise HTTPException(403, "Inventory access is not permitted")
    return user


class InventoryAuthService:
    def __init__(self):
        self.repository = InventoryAuthRepository()

    def login(
        self, session: Session, data: LoginRequest, settings: Settings, host: str | None
    ) -> LoginData:
        signing_key(settings)
        try:
            user = self.repository.by_username(session, data.username.strip())
            valid = verify_password(
                data.password.get_secret_value(), user.password_hash if user else None
            )
            if not valid or user is None or user.status != "ACTIVE":
                raise HTTPException(401, "Invalid username or password")
            principal = check_access(self.repository.principal(session, user))
            token = issue_token(user.user_id, settings)
            user.last_login_at = datetime.now(UTC)
            self.repository.audit(session, user.user_id, "INVENTORY_LOGIN", host)
            session.commit()
            return LoginData(
                access_token=token,
                expires_in=settings.inventory_access_token_expire_minutes * 60,
                user=principal,
            )
        except SQLAlchemyError as error:
            session.rollback()
            raise HTTPException(503, "Inventory authentication storage is unavailable") from error

    def current_user(self, session: Session, user_id: int) -> InventoryUser:
        try:
            user = self.repository.by_id(session, user_id)
            if user is None or user.status != "ACTIVE":
                raise HTTPException(401, "Inventory session is no longer valid")
            return self.repository.principal(session, user)
        except SQLAlchemyError as error:
            session.rollback()
            raise HTTPException(503, "Inventory authentication storage is unavailable") from error

    def logout(self, session: Session, user: InventoryUser, host: str | None) -> None:
        try:
            self.repository.audit(session, user.user_id, "INVENTORY_LOGOUT", host)
            session.commit()
        except SQLAlchemyError as error:
            session.rollback()
            raise HTTPException(503, "Inventory authentication storage is unavailable") from error
