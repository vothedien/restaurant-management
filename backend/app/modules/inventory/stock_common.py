"""Shared transaction, numeric and locking rules for inventory workflows."""

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError, BusinessRuleError, ConflictError, NotFoundError
from app.db.models.catalog import Ingredient
from app.db.models.inventory import StockLot, StockMovement
from app.db.models.rbac import User


class StockStorageError(ApplicationError):
    status_code = 503


@contextmanager
def database_errors(session: Session) -> Iterator[None]:
    try:
        yield
    except IntegrityError as error:
        session.rollback()
        raise ConflictError(
            "Stock data conflicts with an existing record or concurrent change"
        ) from error
    except SQLAlchemyError as error:
        session.rollback()
        raise StockStorageError("Stock storage is temporarily unavailable") from error
    except Exception:
        session.rollback()
        raise


@contextmanager
def transaction(session: Session) -> Iterator[None]:
    # Autobegin accommodates a caller's preceding reads; one service owns commit.
    # Inner allocation helpers never commit. Render response models before commit.
    with database_errors(session):
        yield
        session.commit()


def _numeric(value: Decimal, scale: int, *, exact: bool) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise BusinessRuleError("A finite Decimal value is required")
    try:
        with localcontext() as context:
            context.prec = 40
            rounded = value.quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_UP)
    except InvalidOperation as error:
        raise BusinessRuleError("Value exceeds database numeric precision") from error
    if abs(rounded) >= Decimal(10) ** (14 - scale):
        raise BusinessRuleError("Value exceeds database numeric precision")
    if exact and value != rounded:
        raise BusinessRuleError("Base quantities must be exactly representable to 0.001")
    return rounded


def exact_quantity(value: Decimal) -> Decimal:
    return _numeric(value, 3, exact=True)


def money(value: Decimal) -> Decimal:
    return _numeric(value, 2, exact=False)


def unit_cost(value: Decimal) -> Decimal:
    return _numeric(value, 4, exact=False)


def stock_now(session: Session) -> datetime:
    # PostgreSQL CURRENT_TIMESTAMP is transaction-start time, which may precede
    # a stocktake snapshot while a writer was waiting for its ingredient lock.
    if session.get_bind().dialect.name == "postgresql":
        return session.scalar(select(func.clock_timestamp()))
    return datetime.now(UTC)


def require_actor(session: Session, user_id: int | None) -> User | None:
    # There is no authentication dependency in the existing application yet.
    # This validates the FK only; it must not be presented as authorization.
    if user_id is None:
        return None
    actor = session.get(User, user_id)
    if actor is None:
        raise NotFoundError("User not found")
    if actor.status != "ACTIVE":
        raise BusinessRuleError("User must be active")
    return actor


def lock_ingredients(
    session: Session, ids: Iterable[int], *, active: bool = True
) -> dict[int, Ingredient]:
    ingredient_ids = sorted(set(ids))
    rows = list(
        session.scalars(
            select(Ingredient)
            .where(Ingredient.ingredient_id.in_(ingredient_ids))
            .order_by(Ingredient.ingredient_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    if len(rows) != len(ingredient_ids):
        raise NotFoundError("Ingredient not found")
    if active and any(row.status != "ACTIVE" for row in rows):
        raise BusinessRuleError("Ingredients must be active")
    return {row.ingredient_id: row for row in rows}


def add_movement(
    session: Session,
    lot: StockLot,
    *,
    movement_type: str,
    direction: str,
    quantity: Decimal,
    performed_by: int | None = None,
    order_item_id: int | None = None,
    goods_receipt_item_id: int | None = None,
    stocktake_item_id: int | None = None,
    reason: str | None = None,
) -> StockMovement:
    quantity = exact_quantity(quantity)
    if quantity <= 0:
        raise BusinessRuleError("Movement quantity must be positive")
    movement = StockMovement(
        movement_number=f"SM-{uuid4().hex}",
        ingredient_id=lot.ingredient_id,
        stock_lot_id=lot.stock_lot_id,
        movement_type=movement_type,
        direction=direction,
        quantity=quantity,
        occurred_at=stock_now(session),
        performed_by=performed_by,
        order_item_id=order_item_id,
        goods_receipt_item_id=goods_receipt_item_id,
        stocktake_item_id=stocktake_item_id,
        reason=reason,
    )
    session.add(movement)
    return movement
