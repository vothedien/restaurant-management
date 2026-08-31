from sqlalchemy.orm import Session

from app.db.models.catalog import DiningTable
from app.modules.sales.repository import DiningTableRepository


class SalesService:
    def __init__(self, repository: DiningTableRepository | None = None) -> None:
        self.repository = repository or DiningTableRepository()

    def list_tables(
        self, session: Session, *, status: str | None, limit: int, offset: int
    ) -> list[DiningTable]:
        return self.repository.list(session, status=status, limit=limit, offset=offset)
