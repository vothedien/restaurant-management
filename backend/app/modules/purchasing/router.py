from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.modules.purchasing.schemas import (
    MAX_BIGINT,
    SupplierCreate,
    SupplierIngredientCreate,
    SupplierIngredientListData,
    SupplierIngredientUpdate,
    SupplierListData,
    SupplierStatus,
    SupplierUpdate,
)
from app.modules.purchasing.service import PurchasingService

router = APIRouter(prefix="/purchasing", tags=["purchasing"])
service = PurchasingService()

ResourceId = Annotated[int, Path(gt=0, le=MAX_BIGINT)]


@router.get("/suppliers")
def list_suppliers(
    session: Annotated[Session, Depends(get_db)],
    search: str | None = Query(default=None, max_length=180),
    status_filter: Annotated[SupplierStatus | None, Query(alias="status")] = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    suppliers, total = service.list_suppliers(
        session,
        search=search.strip() if search else None,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    data = SupplierListData(items=suppliers, total=total, limit=limit, offset=offset)
    return success_response("Suppliers retrieved", data.model_dump(mode="json"))


@router.get("/suppliers/{supplier_id}")
def get_supplier(
    supplier_id: ResourceId, session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    supplier = service.get_supplier(session, supplier_id)
    return success_response("Supplier retrieved", supplier.model_dump(mode="json"))


@router.post("/suppliers", status_code=status.HTTP_201_CREATED)
def create_supplier(
    data: SupplierCreate, session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    supplier = service.create_supplier(session, data)
    return success_response("Supplier created", supplier.model_dump(mode="json"))


@router.patch("/suppliers/{supplier_id}")
def update_supplier(
    supplier_id: ResourceId,
    data: SupplierUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    supplier = service.update_supplier(session, supplier_id, data)
    return success_response("Supplier updated", supplier.model_dump(mode="json"))


@router.delete("/suppliers/{supplier_id}")
def delete_supplier(
    supplier_id: ResourceId, session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    supplier = service.deactivate_supplier(session, supplier_id)
    return success_response("Supplier deactivated", supplier.model_dump(mode="json"))


@router.get("/supplier-ingredients")
def list_supplier_ingredients(
    session: Annotated[Session, Depends(get_db)],
    supplier_id: int | None = Query(default=None, gt=0, le=MAX_BIGINT),
    ingredient_id: int | None = Query(default=None, gt=0, le=MAX_BIGINT),
    is_active: bool | None = None,
    is_preferred: bool | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    mappings, total = service.list_supplier_ingredients(
        session,
        supplier_id=supplier_id,
        ingredient_id=ingredient_id,
        is_active=is_active,
        is_preferred=is_preferred,
        limit=limit,
        offset=offset,
    )
    data = SupplierIngredientListData(items=mappings, total=total, limit=limit, offset=offset)
    return success_response("Supplier ingredients retrieved", data.model_dump(mode="json"))


@router.get("/supplier-ingredients/{supplier_ingredient_id}")
def get_supplier_ingredient(
    supplier_ingredient_id: ResourceId, session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    mapping = service.get_supplier_ingredient(session, supplier_ingredient_id)
    return success_response("Supplier ingredient retrieved", mapping.model_dump(mode="json"))


@router.post("/supplier-ingredients", status_code=status.HTTP_201_CREATED)
def create_supplier_ingredient(
    data: SupplierIngredientCreate, session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    mapping = service.create_supplier_ingredient(session, data)
    return success_response("Supplier ingredient created", mapping.model_dump(mode="json"))


@router.patch("/supplier-ingredients/{supplier_ingredient_id}")
def update_supplier_ingredient(
    supplier_ingredient_id: ResourceId,
    data: SupplierIngredientUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    mapping = service.update_supplier_ingredient(session, supplier_ingredient_id, data)
    return success_response("Supplier ingredient updated", mapping.model_dump(mode="json"))


@router.delete("/supplier-ingredients/{supplier_ingredient_id}")
def delete_supplier_ingredient(
    supplier_ingredient_id: ResourceId, session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    mapping = service.deactivate_supplier_ingredient(session, supplier_ingredient_id)
    return success_response("Supplier ingredient deactivated", mapping.model_dump(mode="json"))
