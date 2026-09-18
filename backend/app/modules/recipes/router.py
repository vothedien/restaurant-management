from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.modules.inventory_auth.dependencies import (
    InventoryActor,
    require_inventory_permission,
)
from app.modules.recipes.schemas import (
    RecipeCreate,
    RecipeItemsReplace,
    RecipeListData,
    RecipeRead,
    RecipeStatus,
    RecipeUpdate,
)
from app.modules.recipes.service import RecipesService

router = APIRouter(prefix="/recipes", tags=["recipes"])
service = RecipesService()


@router.get("", dependencies=[Depends(require_inventory_permission("RECIPE_MANAGE"))])
def list_recipes(
    session: Annotated[Session, Depends(get_db)],
    dish_id: int | None = Query(default=None, gt=0),
    status_filter: Annotated[RecipeStatus | None, Query(alias="status")] = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    recipes, total = service.list_recipes(
        session, dish_id=dish_id, status=status_filter, limit=limit, offset=offset
    )
    data = RecipeListData(
        items=[RecipeRead.model_validate(recipe) for recipe in recipes],
        total=total,
        limit=limit,
        offset=offset,
    )
    return success_response("Recipe versions retrieved", data.model_dump(mode="json"))


@router.get(
    "/dishes/{dish_id}/active",
    dependencies=[Depends(require_inventory_permission("RECIPE_MANAGE"))],
)
def get_active_recipe(
    dish_id: int, session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    data = service.get_active_recipe(session, dish_id)
    return success_response("Active recipe retrieved", data.model_dump(mode="json"))


@router.get(
    "/{recipe_version_id}", dependencies=[Depends(require_inventory_permission("RECIPE_MANAGE"))]
)
def get_recipe(
    recipe_version_id: int, session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    data = service.get_recipe(session, recipe_version_id)
    return success_response("Recipe version retrieved", data.model_dump(mode="json"))


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_inventory_permission("RECIPE_MANAGE"))],
)
def create_recipe(
    data: RecipeCreate, session: Annotated[Session, Depends(get_db)], actor: InventoryActor
) -> dict[str, object]:
    recipe = service.create_recipe(session, data, created_by=actor.user_id)
    return success_response("Recipe version created", recipe.model_dump(mode="json"))


@router.patch(
    "/{recipe_version_id}", dependencies=[Depends(require_inventory_permission("RECIPE_MANAGE"))]
)
def update_recipe(
    recipe_version_id: int,
    data: RecipeUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    recipe = service.update_recipe(session, recipe_version_id, data)
    return success_response("Recipe version updated", recipe.model_dump(mode="json"))


@router.put(
    "/{recipe_version_id}/items",
    dependencies=[Depends(require_inventory_permission("RECIPE_MANAGE"))],
)
def replace_items(
    recipe_version_id: int,
    data: RecipeItemsReplace,
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    recipe = service.replace_items(session, recipe_version_id, data)
    return success_response("Recipe items replaced", recipe.model_dump(mode="json"))


@router.post(
    "/{recipe_version_id}/activate",
    dependencies=[Depends(require_inventory_permission("RECIPE_MANAGE"))],
)
def activate_recipe(
    recipe_version_id: int, session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    recipe = service.activate_recipe(session, recipe_version_id)
    return success_response("Recipe version activated", recipe.model_dump(mode="json"))
