"""Seed the canonical inventory units and conversions without creating duplicates.

Run manually from the backend directory after reviewing the local DATABASE_URL:
    python scripts/seed_inventory_units.py
"""

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.catalog import Unit, UnitConversion
from app.db.session import get_session_factory

UNITS: Sequence[dict[str, str]] = (
    {"unit_code": "G", "unit_name": "Gram", "dimension": "MASS"},
    {"unit_code": "KG", "unit_name": "Kilogram", "dimension": "MASS"},
    {"unit_code": "ML", "unit_name": "Milliliter", "dimension": "VOLUME"},
    {"unit_code": "L", "unit_name": "Liter", "dimension": "VOLUME"},
    {"unit_code": "PCS", "unit_name": "Piece", "dimension": "COUNT"},
)
CONVERSIONS: Sequence[tuple[str, str, Decimal]] = (
    ("KG", "G", Decimal("1000")),
    ("L", "ML", Decimal("1000")),
)


def seed_inventory_units(session: Session) -> tuple[int, int]:
    """Insert missing canonical units and conversions, returning their creation counts."""

    codes = [unit["unit_code"] for unit in UNITS]
    units_by_code = {
        unit.unit_code: unit
        for unit in session.scalars(select(Unit).where(Unit.unit_code.in_(codes)))
    }
    created_units = 0
    for data in UNITS:
        unit = units_by_code.get(data["unit_code"])
        if unit is None:
            unit = Unit(**data, is_active=True)
            session.add(unit)
            units_by_code[unit.unit_code] = unit
            created_units += 1
        elif unit.dimension != data["dimension"]:
            raise ValueError(
                f"Existing unit {unit.unit_code} has dimension {unit.dimension}, "
                f"expected {data['dimension']}."
            )
        elif not unit.is_active:
            unit.is_active = True

    session.flush()
    created_conversions = 0
    for from_code, to_code, factor in CONVERSIONS:
        from_unit = units_by_code[from_code]
        to_unit = units_by_code[to_code]
        conversion = session.scalar(
            select(UnitConversion).where(
                UnitConversion.from_unit_id == from_unit.unit_id,
                UnitConversion.to_unit_id == to_unit.unit_id,
            )
        )
        if conversion is None:
            session.add(
                UnitConversion(
                    from_unit_id=from_unit.unit_id,
                    to_unit_id=to_unit.unit_id,
                    factor=factor,
                )
            )
            created_conversions += 1
        elif conversion.factor != factor:
            raise ValueError(
                f"Existing conversion {from_code} to {to_code} has factor {conversion.factor}, "
                f"expected {factor}."
            )
    return created_units, created_conversions


def main() -> None:
    session = get_session_factory()()
    try:
        created_units, created_conversions = seed_inventory_units(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    print(
        "Inventory seed completed: "
        f"{created_units} unit(s) and {created_conversions} conversion(s) created."
    )


if __name__ == "__main__":
    main()
