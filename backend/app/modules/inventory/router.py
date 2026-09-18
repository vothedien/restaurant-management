from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.modules.inventory.schemas import (
    IngredientCreate,
    IngredientListData,
    IngredientRead,
    IngredientStatus,
    IngredientUpdate,
    UnitConversionCreate,
    UnitConversionListData,
    UnitConversionRead,
    UnitConversionUpdate,
    UnitCreate,
    UnitListData,
    UnitRead,
    UnitUpdate,
)
from app.modules.inventory.service import InventoryService
from app.modules.inventory.stock_router import router as stock_router
from app.modules.inventory.stocktake_router import router as stocktake_router
from app.modules.inventory_auth.dependencies import (
    require_inventory_access,
    require_inventory_permission,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])
router.include_router(stock_router)
router.include_router(stocktake_router)
service = InventoryService()


def _unit_data(unit: object) -> dict[str, object]:
    return UnitRead.model_validate(unit).model_dump(mode="json")


def _conversion_data(conversion: object) -> dict[str, object]:
    return UnitConversionRead.model_validate(conversion).model_dump(mode="json")


def _ingredient_data(ingredient: object) -> dict[str, object]:
    return IngredientRead.model_validate(ingredient).model_dump(mode="json")


@router.get("/units", dependencies=[Depends(require_inventory_access)])
def list_units(
    session: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=80),
) -> dict[str, object]:
    units, total = service.list_units(
        session, limit=limit, offset=offset, search=search.strip() if search else None
    )
    data = UnitListData(
        items=[UnitRead.model_validate(unit) for unit in units],
        total=total,
        limit=limit,
        offset=offset,
    )
    return success_response("Units retrieved", data.model_dump(mode="json"))


@router.get("/units/{unit_id}", dependencies=[Depends(require_inventory_access)])
def get_unit(session: Annotated[Session, Depends(get_db)], unit_id: int) -> dict[str, object]:
    return success_response("Unit retrieved", _unit_data(service.get_unit(session, unit_id)))


@router.post(
    "/units",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_inventory_permission("INVENTORY_MANAGE"))],
)
def create_unit(
    data: UnitCreate, session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    return success_response("Unit created", _unit_data(service.create_unit(session, data)))


@router.patch(
    "/units/{unit_id}", dependencies=[Depends(require_inventory_permission("INVENTORY_MANAGE"))]
)
def update_unit(
    unit_id: int, data: UnitUpdate, session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    return success_response("Unit updated", _unit_data(service.update_unit(session, unit_id, data)))


@router.delete(
    "/units/{unit_id}", dependencies=[Depends(require_inventory_permission("INVENTORY_MANAGE"))]
)
def delete_unit(session: Annotated[Session, Depends(get_db)], unit_id: int) -> dict[str, object]:
    return success_response(
        "Unit deactivated", _unit_data(service.deactivate_unit(session, unit_id))
    )


@router.get("/unit-conversions", dependencies=[Depends(require_inventory_access)])
def list_conversions(
    session: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    conversions, total = service.list_conversions(session, limit=limit, offset=offset)
    data = UnitConversionListData(
        items=[UnitConversionRead.model_validate(conversion) for conversion in conversions],
        total=total,
        limit=limit,
        offset=offset,
    )
    return success_response("Unit conversions retrieved", data.model_dump(mode="json"))


@router.get("/unit-conversions/{conversion_id}", dependencies=[Depends(require_inventory_access)])
def get_conversion(
    session: Annotated[Session, Depends(get_db)], conversion_id: int
) -> dict[str, object]:
    return success_response(
        "Unit conversion retrieved",
        _conversion_data(service.get_conversion(session, conversion_id)),
    )


@router.post(
    "/unit-conversions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_inventory_permission("INVENTORY_MANAGE"))],
)
def create_conversion(
    data: UnitConversionCreate, session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    return success_response(
        "Unit conversion created", _conversion_data(service.create_conversion(session, data))
    )


@router.patch(
    "/unit-conversions/{conversion_id}",
    dependencies=[Depends(require_inventory_permission("INVENTORY_MANAGE"))],
)
def update_conversion(
    conversion_id: int,
    data: UnitConversionUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    return success_response(
        "Unit conversion updated",
        _conversion_data(service.update_conversion(session, conversion_id, data)),
    )


@router.delete(
    "/unit-conversions/{conversion_id}",
    dependencies=[Depends(require_inventory_permission("INVENTORY_MANAGE"))],
)
def delete_conversion(
    session: Annotated[Session, Depends(get_db)], conversion_id: int
) -> JSONResponse:
    service.delete_conversion(session, conversion_id)
    return JSONResponse(
        content=success_response("Unit conversion deleted", {"conversion_id": conversion_id})
    )


@router.get("/ingredients", dependencies=[Depends(require_inventory_access)])
def list_ingredients(
    session: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=150),
    status_filter: Annotated[IngredientStatus | None, Query(alias="status")] = None,
) -> dict[str, object]:
    ingredients, total = service.list_ingredients(
        session,
        limit=limit,
        offset=offset,
        search=search.strip() if search else None,
        status=status_filter,
    )
    data = IngredientListData(
        items=[IngredientRead.model_validate(ingredient) for ingredient in ingredients],
        total=total,
        limit=limit,
        offset=offset,
    )
    return success_response("Ingredients retrieved", data.model_dump(mode="json"))


@router.get("/ingredients/{ingredient_id}", dependencies=[Depends(require_inventory_access)])
def get_ingredient(
    session: Annotated[Session, Depends(get_db)], ingredient_id: int
) -> dict[str, object]:
    return success_response(
        "Ingredient retrieved",
        _ingredient_data(service.get_ingredient(session, ingredient_id)),
    )


@router.post(
    "/ingredients",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_inventory_permission("INVENTORY_MANAGE"))],
)
def create_ingredient(
    data: IngredientCreate, session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    return success_response(
        "Ingredient created", _ingredient_data(service.create_ingredient(session, data))
    )


@router.patch(
    "/ingredients/{ingredient_id}",
    dependencies=[Depends(require_inventory_permission("INVENTORY_MANAGE"))],
)
def update_ingredient(
    ingredient_id: int,
    data: IngredientUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    return success_response(
        "Ingredient updated",
        _ingredient_data(service.update_ingredient(session, ingredient_id, data)),
    )


@router.delete(
    "/ingredients/{ingredient_id}",
    dependencies=[Depends(require_inventory_permission("INVENTORY_MANAGE"))],
)
def delete_ingredient(
    session: Annotated[Session, Depends(get_db)], ingredient_id: int
) -> dict[str, object]:
    return success_response(
        "Ingredient deactivated",
        _ingredient_data(service.deactivate_ingredient(session, ingredient_id)),
    )
