from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.modules.sales.schemas import DiningTableListData, DiningTableRead
from app.modules.sales.service import SalesService

router = APIRouter(prefix="/sales", tags=["sales"])
service = SalesService()


@router.get("/tables")
def list_tables(
    session: Annotated[Session, Depends(get_db)],
    status: str | None = Query(default=None, min_length=1, max_length=20),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    tables = service.list_tables(session, status=status, limit=limit, offset=offset)
    data = DiningTableListData(
        items=[DiningTableRead.model_validate(table) for table in tables],
        status=status,
        limit=limit,
        offset=offset,
    )
    return success_response("Dining tables retrieved", data.model_dump(mode="json"))
