from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.catalog import DiningTable


class DiningTableRepository:
    def list(
        self, session: Session, *, status: str | None, limit: int, offset: int
    ) -> list[DiningTable]:
        statement = select(DiningTable).order_by(DiningTable.table_id)
        if status:
            statement = statement.where(DiningTable.status == status)
        return list(session.scalars(statement.limit(limit).offset(offset)))
