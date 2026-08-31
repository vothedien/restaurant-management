from sqlalchemy.orm import Session

from app.db.models.catalog import Ingredient
from app.modules.inventory.repository import IngredientRepository


class InventoryService:
    def __init__(self, repository: IngredientRepository | None = None) -> None:
        self.repository = repository or IngredientRepository()

    def list_ingredients(self, session: Session, *, limit: int, offset: int) -> list[Ingredient]:
        return self.repository.list(session, limit=limit, offset=offset)
