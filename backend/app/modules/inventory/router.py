from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.modules.inventory.schemas import IngredientListData, IngredientRead
from app.modules.inventory.service import InventoryService

router = APIRouter(prefix="/inventory", tags=["inventory"])
service = InventoryService()


@router.get("/ingredients")
def list_ingredients(
    session: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    ingredients = service.list_ingredients(session, limit=limit, offset=offset)
    data = IngredientListData(
        items=[IngredientRead.model_validate(ingredient) for ingredient in ingredients],
        limit=limit,
        offset=offset,
    )
    return success_response("Ingredients retrieved", data.model_dump(mode="json"))
