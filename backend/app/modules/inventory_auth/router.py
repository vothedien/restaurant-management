from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.responses import success_response
from app.db.session import get_db
from app.modules.inventory_auth.dependencies import (
    get_current_inventory_user,
)
from app.modules.inventory_auth.schemas import InventoryUser, LoginRequest
from app.modules.inventory_auth.security import signing_key
from app.modules.inventory_auth.service import InventoryAuthService


def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/inventory-auth", tags=["inventory auth"], dependencies=[Depends(no_store)]
)
service = InventoryAuthService()


@router.get("/status")
def auth_status(settings: Annotated[Settings, Depends(get_settings)]):
    try:
        signing_key(settings)
        configured = True
    except HTTPException:
        configured = False
    return success_response(
        "Inventory authentication status", {"implemented": True, "configured": configured}
    )


@router.post("/login")
def login(
    data: LoginRequest,
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    result = service.login(session, data, settings, request.client.host if request.client else None)
    return success_response("Inventory login successful", result.model_dump(mode="json"))


@router.get("/me")
def me(user: Annotated[InventoryUser, Depends(get_current_inventory_user)]):
    return success_response("Inventory user retrieved", {"user": user.model_dump(mode="json")})


@router.post("/logout")
def logout(
    request: Request,
    user: Annotated[InventoryUser, Depends(get_current_inventory_user)],
    session: Annotated[Session, Depends(get_db)],
):
    service.logout(session, user, request.client.host if request.client else None)
    return success_response(
        "Clear the client Inventory session; issued tokens expire normally", {"stateless": True}
    )
