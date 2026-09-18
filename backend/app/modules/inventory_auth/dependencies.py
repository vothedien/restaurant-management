from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.modules.inventory_auth.schemas import InventoryUser
from app.modules.inventory_auth.security import decode_subject
from app.modules.inventory_auth.service import InventoryAuthService, check_access

bearer = HTTPBearer(auto_error=False, scheme_name="InventoryBearer")
service = InventoryAuthService()


def inventory_subject(
    credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> int:
    if credential is None or credential.scheme.lower() != "bearer":
        raise HTTPException(401, "Inventory Bearer token is required")
    return decode_subject(credential.credentials, settings)


def get_current_inventory_user(
    subject: Annotated[int, Depends(inventory_subject)],
    session: Annotated[Session, Depends(get_db)],
) -> InventoryUser:
    return service.current_user(session, subject)


def require_inventory_access(
    user: Annotated[InventoryUser, Depends(get_current_inventory_user)],
) -> InventoryUser:
    return check_access(user)


def require_inventory_permission(*codes: str):
    if not codes:
        raise ValueError("At least one Inventory permission must be specified")

    def require(user: Annotated[InventoryUser, Depends(require_inventory_access)]) -> InventoryUser:
        if not set(codes).intersection(user.permissions):
            raise HTTPException(403, "Insufficient Inventory permission")
        return user

    return require


InventoryActor = Annotated[InventoryUser, Depends(require_inventory_access)]
