from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DiningTableRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    table_id: int
    table_code: str
    table_name: str | None
    capacity: int
    status: str
    created_at: datetime


class DiningTableListData(BaseModel):
    items: list[DiningTableRead]
    status: str | None
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
