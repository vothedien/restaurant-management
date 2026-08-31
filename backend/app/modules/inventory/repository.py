from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.catalog import Ingredient


class IngredientRepository:
    def list(self, session: Session, *, limit: int, offset: int) -> list[Ingredient]:
        statement = (
            select(Ingredient).order_by(Ingredient.ingredient_id).limit(limit).offset(offset)
        )
        return list(session.scalars(statement))
