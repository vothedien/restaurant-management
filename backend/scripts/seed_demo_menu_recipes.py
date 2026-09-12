"""Reviewable pizza demo data; no database access unless explicitly requested.

From backend (Python 3.11+):
    python scripts/seed_demo_menu_recipes.py --validate-only  # also the default
    python scripts/seed_demo_menu_recipes.py --dry-run        # insert, then rollback
    python scripts/seed_demo_menu_recipes.py --apply          # one transaction/commit

Review names, codes, categories and prices with Person 1 before using database modes.
All 20 pizza_id/pizza_type_id/size triples were verified on 2026-09-12 against
pizzas.csv (96 rows) from the public Pizza Place Sales mirror:
https://raw.githubusercontent.com/bhaskarguru/Pizza-Place-Sales-Analysis/main/pizzas.csv
CSV SHA256: 323c29b4dc2321c26153b5d56483225b2ea2986826315700141689aac5327706
The Maven download returned 404; verification used the mirror, not the Maven file.
The downloaded CSV is kept only in ignored tmp/pizza-place-verification/.
The script itself does not download or require that file. Toppings remain demo
choices. Prices are demo VND, NOT prices from pizzas.csv.
Shelf lives/stock thresholds are demo planning defaults, not food-storage guidance.

Requires canonical units/conversions from seed_inventory_units.py to exist already.
This script never changes units, schema, existing rows, stock lots or movements.
An existing recipe must match completely, including its ingredient set; missing
items on an existing recipe are a conflict (they may have been deliberately removed).
Dry-run rolls back rows, but PostgreSQL identity sequences can still advance.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

RECIPE_DISCLAIMER = (
    "Dữ liệu công thức mô phỏng cho mục đích đồ án, không phải định lượng gốc từ Pizza Place Sales."
)
PRICE_DISCLAIMER = "Giá demo tính bằng VND, không phải giá từ pizzas.csv."
RECIPE_METADATA = {
    "version_no": 1,
    "status": "ACTIVE",
    # Fixed on purpose: rerunning tomorrow must not change the recipe's identity.
    "effective_from": date(2026, 9, 1),
    "effective_to": None,
    "created_by": None,
    "notes": f"[demo-menu-recipes:v1] {RECIPE_DISCLAIMER}",
}
BASE_UNIT_DIMENSIONS = {"G": "MASS", "ML": "VOLUME", "PCS": "COUNT"}
SIZE_ORDER = ("s", "m", "l")
# Independent acceptance list, not derived from DISHES or RECIPES.
EXPECTED_DISH_CODES = frozenset(
    "classic_dlx_s classic_dlx_m classic_dlx_l "
    "bbq_ckn_s bbq_ckn_m bbq_ckn_l "
    "hawaiian_s hawaiian_m hawaiian_l "
    "pepperoni_s pepperoni_m pepperoni_l "
    "thai_ckn_s thai_ckn_m thai_ckn_l "
    "veggie_veg_s veggie_veg_m veggie_veg_l mexicana_s mexicana_m".split()
)

CATEGORIES = [
    {
        "category_code": code,
        "category_name": name,
        "description": "Danh mục pizza demo cho đồ án.",
        "display_order": order,
        "status": "ACTIVE",
    }
    for code, name, order in (
        ("PIZZA_CLASSIC", "Classic Pizza", 10),
        ("PIZZA_CHICKEN", "Chicken Pizza", 20),
        ("PIZZA_VEGGIE", "Veggie Pizza", 30),
    )
]

# Names/category and size prices are reviewable here; prices are demo VND.
PIZZA_TYPES = {
    "classic_dlx": ("Classic Deluxe Pizza", "PIZZA_CLASSIC", (119000, 169000, 219000)),
    "bbq_ckn": ("BBQ Chicken Pizza", "PIZZA_CHICKEN", (129000, 179000, 229000)),
    "hawaiian": ("Hawaiian Pizza", "PIZZA_CLASSIC", (109000, 159000, 209000)),
    "pepperoni": ("Pepperoni Pizza", "PIZZA_CLASSIC", (109000, 159000, 209000)),
    "thai_ckn": ("Thai Chicken Pizza", "PIZZA_CHICKEN", (129000, 179000, 229000)),
    "veggie_veg": ("Vegetables Pizza", "PIZZA_VEGGIE", (99000, 149000, 199000)),
    "mexicana": ("Mexicana Pizza", "PIZZA_VEGGIE", (119000, 169000)),
}
DISHES = [
    {
        "dish_code": f"{pizza_type}_{SIZE_ORDER[index]}",
        "dish_name": f"{name} ({SIZE_ORDER[index].upper()})",
        "category_code": category_code,  # resolved to category_id after query/flush
        "selling_price": Decimal(price),
        "description": f"Pizza demo; mỗi kích cỡ là một SKU riêng. {PRICE_DISCLAIMER}",
        "status": "ACTIVE",
    }
    for pizza_type, (name, category_code, prices) in PIZZA_TYPES.items()
    for index, price in enumerate(prices)
]


def _ingredient(
    code: str, name: str, unit: str, shelf_days: int, minimum: int = 1000, safety: int = 500
) -> dict[str, Any]:
    return {
        "ingredient_code": code,
        "ingredient_name": name,
        "base_unit_code": unit,  # resolved to base_unit_id; never an identity literal
        "manages_lot": True,
        "default_shelf_life_days": shelf_days,
        "minimum_stock_qty": Decimal(minimum),
        "safety_stock_qty": Decimal(safety),
        "status": "ACTIVE",
    }


INGREDIENTS = [
    _ingredient("FLOUR", "Bột mì", "G", 180, 10000, 5000),
    _ingredient("YEAST", "Men khô", "G", 180, 100, 50),
    _ingredient("SALT", "Muối", "G", 365, 500, 250),
    _ingredient("OLIVE_OIL", "Dầu olive", "ML", 365),
    _ingredient("WATER", "Nước lọc dùng làm bột", "ML", 365, 5000, 2500),
    _ingredient("TOMATO_SAUCE", "Sốt cà chua", "ML", 7),
    _ingredient("MOZZARELLA", "Phô mai mozzarella", "G", 7, 3000, 1500),
    _ingredient("PEPPERONI", "Xúc xích pepperoni", "G", 14),
    _ingredient("BACON", "Thịt ba chỉ xông khói", "G", 7),
    # Match the existing DDL CHICKEN seed, including its stock thresholds.
    _ingredient("CHICKEN", "Thịt gà", "G", 3, 5000, 2500),
    _ingredient("BBQ_SAUCE", "Sốt BBQ", "ML", 30),
    _ingredient("THAI_SAUCE", "Sốt Thái", "ML", 14),
    _ingredient("HAM", "Thịt nguội", "G", 5),
    _ingredient("PINEAPPLE", "Dứa", "G", 3),
    _ingredient("RED_PEPPER", "Ớt chuông đỏ", "G", 7),
    _ingredient("GREEN_PEPPER", "Ớt chuông xanh", "G", 7),
    _ingredient("RED_ONION", "Hành tây tím", "G", 14),
    _ingredient("MUSHROOM", "Nấm mỡ", "G", 3),
    _ingredient("TOMATO", "Cà chua", "G", 5),
    _ingredient("CILANTRO", "Rau mùi", "G", 3, 100, 50),
    _ingredient("GARLIC", "Tỏi", "G", 30, 300, 150),
    _ingredient("ZUCCHINI", "Bí ngòi", "G", 7),
    _ingredient("SPINACH", "Rau bina", "G", 3),
    _ingredient("JALAPENO", "Ớt jalapeño", "G", 7, 300, 150),
    _ingredient("CORN", "Bắp hạt", "G", 3),
    _ingredient("CHIPOTLE_SAUCE", "Sốt ớt chipotle", "ML", 14),
]

# All triples below are simulated S/M/L amounts in the ingredient's base unit.
# Dough: flour/water maintain hydration; yeast/salt/oil follow their own small doses.
# Sauce, cheese, meats, vegetables and garnishes each have explicit portion curves.
# Totals are compared separately in G and ML; no density or mass/volume conversion.
DOUGH_PORTIONS = {
    "FLOUR": (120, 180, 250),
    "WATER": (72, 108, 150),
    "YEAST": (1, 1.5, 2),
    "SALT": (2, 3, 4),
    "OLIVE_OIL": (4, 6, 8),
    "MOZZARELLA": (55, 80, 110),
}
TOPPING_PORTIONS = {
    "classic_dlx": {
        "TOMATO_SAUCE": (35, 50, 65),
        "PEPPERONI": (20, 30, 40),
        "BACON": (15, 22, 30),
        "MUSHROOM": (20, 30, 40),
        "RED_ONION": (10, 15, 20),
        "RED_PEPPER": (15, 22, 30),
    },
    "bbq_ckn": {
        "BBQ_SAUCE": (30, 45, 60),
        "CHICKEN": (50, 75, 100),
        "RED_PEPPER": (15, 22, 30),
        "GREEN_PEPPER": (15, 22, 30),
        "RED_ONION": (10, 15, 20),
        "TOMATO": (20, 30, 40),
    },
    "hawaiian": {
        "TOMATO_SAUCE": (35, 50, 65),
        "HAM": (35, 50, 70),
        "PINEAPPLE": (40, 60, 80),
    },
    "pepperoni": {"TOMATO_SAUCE": (35, 50, 65), "PEPPERONI": (35, 50, 70)},
    "thai_ckn": {
        "THAI_SAUCE": (30, 42, 55),
        "CHICKEN": (50, 75, 100),
        "PINEAPPLE": (25, 38, 50),
        "RED_PEPPER": (15, 22, 30),
        "TOMATO": (20, 30, 40),
        "CILANTRO": (2, 3, 4),
    },
    "veggie_veg": {
        "TOMATO_SAUCE": (35, 50, 65),
        "MUSHROOM": (20, 30, 40),
        "TOMATO": (20, 30, 40),
        "RED_PEPPER": (12, 18, 25),
        "GREEN_PEPPER": (12, 18, 25),
        "RED_ONION": (8, 12, 16),
        "ZUCCHINI": (15, 22, 30),
        "SPINACH": (8, 12, 16),
        "GARLIC": (2, 3, 4),
    },
    "mexicana": {
        "CHIPOTLE_SAUCE": (25, 35, 45),
        "TOMATO": (20, 30, 40),
        "RED_PEPPER": (15, 22, 30),
        "JALAPENO": (8, 12, 16),
        "RED_ONION": (10, 15, 20),
        "CILANTRO": (2, 3, 4),
        "CORN": (25, 38, 50),
    },
}
# Independent minimum composition checks catch accidentally deleted base/topping rows.
REQUIRED_TOPPINGS = {
    "classic_dlx": {"PEPPERONI", "BACON", "MUSHROOM", "RED_ONION", "RED_PEPPER"},
    "bbq_ckn": {"CHICKEN", "BBQ_SAUCE"},
    "hawaiian": {"HAM", "PINEAPPLE"},
    "pepperoni": {"PEPPERONI"},
    "thai_ckn": {"CHICKEN", "THAI_SAUCE", "PINEAPPLE", "CILANTRO"},
    "veggie_veg": {"MUSHROOM", "ZUCCHINI", "SPINACH", "GARLIC"},
    "mexicana": {"CHIPOTLE_SAUCE", "JALAPENO", "CORN", "CILANTRO"},
}
RECIPES = {
    dish["dish_code"]: [
        {
            "ingredient_code": ingredient_code,
            "unit_code": next(
                (
                    ingredient["base_unit_code"]
                    for ingredient in INGREDIENTS
                    if ingredient["ingredient_code"] == ingredient_code
                ),
                "UNKNOWN",  # Let offline validation report an unknown ingredient clearly.
            ),
            "quantity": Decimal(str(portions[SIZE_ORDER.index(dish["dish_code"][-1])])),
            "base_quantity": Decimal(str(portions[SIZE_ORDER.index(dish["dish_code"][-1])])),
        }
        # Concatenate instead of dict union so duplicate ingredients are not hidden.
        for ingredient_code, portions in (
            *DOUGH_PORTIONS.items(),
            *TOPPING_PORTIONS.get(dish["dish_code"].rsplit("_", 1)[0], {}).items(),
        )
    ]
    for dish in DISHES
}


class SeedError(Exception):
    """A safe diagnostic containing seed keys/column names, never database values."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SeedError(message)


def _number(value: Any, label: str, scale: int = 3, *, allow_zero: bool = False) -> None:
    _require(isinstance(value, Decimal) and value.is_finite(), f"{label}: finite Decimal required")
    _require(value >= 0 if allow_zero else value > 0, f"{label}: invalid nonpositive value")
    _require(value < Decimal(10) ** (14 - scale), f"{label}: exceeds NUMERIC(14,{scale})")
    _require(value == value.quantize(Decimal(10) ** -scale), f"{label}: too many decimal places")


def _index(rows: list[dict[str, Any]], prefix: str, name_length: int) -> dict[str, Any]:
    code_field, name_field = f"{prefix}_code", f"{prefix}_name"
    for row in rows:
        code, name = row.get(code_field), row.get(name_field)
        _require(isinstance(code, str) and 0 < len(code) <= 40, f"Invalid {code_field}")
        pattern = r"[a-z0-9_]+" if prefix == "dish" else r"[A-Z0-9_]+"
        _require(bool(re.fullmatch(pattern, code)), f"Invalid format for {code_field}: {code}")
        _require(
            isinstance(name, str) and bool(name.strip()) and len(name) <= name_length,
            f"{code}: invalid {name_field}",
        )
        _require(row.get("status") == "ACTIVE", f"{code}: demo status must be ACTIVE")
    counts = Counter(row[code_field] for row in rows)
    duplicates = sorted(code for code, count in counts.items() if count > 1)
    _require(not duplicates, f"Duplicate {code_field}: {', '.join(duplicates)}")
    return {row[code_field]: row for row in rows}


def validate_data() -> None:
    """Validate all materialized data using only the standard library, offline."""
    categories = _index(CATEGORIES, "category", 120)
    dishes = _index(DISHES, "dish", 150)
    ingredients = _index(INGREDIENTS, "ingredient", 150)
    _require(len(dishes) == 20, "Exactly 20 unique dish codes are required")
    _require(set(dishes) == EXPECTED_DISH_CODES, "Dish codes differ from the requested 20 SKUs")
    _require(18 <= len(ingredients) <= 30, "Expected 18-30 ingredients")
    _require(set(RECIPES) == set(dishes), "Recipes must cover every dish with no unknown codes")
    for code, row in categories.items():
        _require(
            type(row["display_order"]) is int and row["display_order"] >= 0,
            f"{code}: invalid display_order",
        )
    for code, row in ingredients.items():
        _require(row["base_unit_code"] in BASE_UNIT_DIMENSIONS, f"{code}: use G, ML or PCS")
        _require(row["manages_lot"] is True, f"{code}: demo ingredients require lot tracking")
        days = row["default_shelf_life_days"]
        _require(type(days) is int and 0 < days <= 730, f"{code}: invalid demo shelf life")
        for field in ("minimum_stock_qty", "safety_stock_qty"):
            _number(row[field], f"{code}.{field}", allow_zero=True)

    _require(RECIPE_METADATA["version_no"] == 1, "Demo recipe version_no must be 1")
    _require(RECIPE_METADATA["status"] == "ACTIVE", "Demo recipe status must be ACTIVE")
    start, end = RECIPE_METADATA["effective_from"], RECIPE_METADATA["effective_to"]
    _require(isinstance(start, date) and start <= date.today(), "Recipe is not effective yet")
    _require(
        end is None or (isinstance(end, date) and end >= date.today() and end >= start),
        "Recipe has invalid or expired effective_to",
    )
    _require(RECIPE_DISCLAIMER in RECIPE_METADATA["notes"], "Missing recipe disclaimer")

    totals: dict[str, dict[str, Decimal]] = {}
    quantities: dict[str, dict[str, Decimal]] = {}
    used_ingredients: set[str] = set()
    for code, dish in dishes.items():
        pizza_type, size = code.rsplit("_", 1)
        _require(dish["category_code"] in categories, f"{code}: unknown category")
        _require(
            size in SIZE_ORDER and dish["dish_name"].endswith(f"({size.upper()})"),
            f"{code}: name/size mismatch",
        )
        _number(dish["selling_price"], f"{code}.selling_price", scale=2)
        items = RECIPES[code]
        _require(bool(items), f"{code}: empty recipe")
        counts = Counter(item["ingredient_code"] for item in items)
        _require(all(count == 1 for count in counts.values()), f"{code}: duplicate recipe item")
        required = {"FLOUR", "WATER", "YEAST", "SALT", "OLIVE_OIL", "MOZZARELLA"}
        _require(
            required | REQUIRED_TOPPINGS[pizza_type] <= counts.keys(),
            f"{code}: missing dough, cheese or characteristic toppings",
        )
        _require(
            bool({"TOMATO_SAUCE", "BBQ_SAUCE", "THAI_SAUCE", "CHIPOTLE_SAUCE"} & counts.keys()),
            f"{code}: missing sauce",
        )
        totals[code] = defaultdict(Decimal)
        quantities[code] = {}
        for item in items:
            ingredient_code = item["ingredient_code"]
            label = f"{code}/{ingredient_code}"
            _require(ingredient_code in ingredients, f"{label}: unknown ingredient")
            base_unit = ingredients[ingredient_code]["base_unit_code"]
            unit = item["unit_code"]
            _require(unit in BASE_UNIT_DIMENSIONS, f"{label}: use base units only")
            _require(
                BASE_UNIT_DIMENSIONS[unit] == BASE_UNIT_DIMENSIONS[base_unit],
                f"{label}: cross-dimension conversion is forbidden",
            )
            _require(unit == base_unit, f"{label}: demo must use the ingredient base unit")
            _number(item["quantity"], f"{label}.quantity")
            _number(item["base_quantity"], f"{label}.base_quantity")
            _require(item["quantity"] == item["base_quantity"], f"{label}: wrong base_quantity")
            totals[code][BASE_UNIT_DIMENSIONS[base_unit]] += item["base_quantity"]
            quantities[code][ingredient_code] = item["base_quantity"]
            used_ingredients.add(ingredient_code)
    _require(used_ingredients == set(ingredients), "Unused demo ingredients found")
    for pizza_type in PIZZA_TYPES:
        codes = [f"{pizza_type}_{size}" for size in SIZE_ORDER if f"{pizza_type}_{size}" in dishes]
        for smaller, larger in zip(codes, codes[1:], strict=False):
            _require(
                dishes[larger]["selling_price"] > dishes[smaller]["selling_price"],
                f"{pizza_type}: prices must increase with size",
            )
            _require(
                quantities[smaller].keys() == quantities[larger].keys(),
                f"{pizza_type}: ingredient sets must agree across sizes",
            )
            for dimension, total in totals[smaller].items():
                _require(
                    totals[larger][dimension] >= total,
                    f"{pizza_type}: {dimension} total decreases with size",
                )
            for ingredient_code, quantity in quantities[smaller].items():
                _require(
                    quantities[larger][ingredient_code] >= quantity,
                    f"{pizza_type}/{ingredient_code}: portion decreases with size",
                )


@dataclass
class Counts:
    planned: int
    inserted: int = 0
    skipped: int = 0
    conflict: int = 0


def planned_counts() -> dict[str, Counts]:
    return {
        "Categories": Counts(len(CATEGORIES)),
        "Dishes": Counts(len(DISHES)),
        "Ingredients": Counts(len(INGREDIENTS)),
        "Recipe versions": Counts(len(RECIPES)),
        "Recipe items": Counts(sum(len(items) for items in RECIPES.values())),
    }


def print_summary(counts: dict[str, Counts]) -> None:
    print("Counts: planned / inserted / skipped / conflict")
    for label, count in counts.items():
        print(f"{label}: {count.planned} / {count.inserted} / {count.skipped} / {count.conflict}")


def _matching(existing: Any, expected: dict[str, Any], label: str, count: Counts) -> None:
    differences = [field for field, value in expected.items() if getattr(existing, field) != value]
    if differences:
        count.conflict += 1
        # Do not echo existing database contents (including notes/descriptions).
        raise SeedError(f"{label}: conflict in {', '.join(differences)}; no overwrite allowed")


def _ensure(session: Session, model: Any, key: str, data: dict[str, Any], count: Counts) -> Any:
    from sqlalchemy import select

    existing = session.scalar(
        select(model).where(getattr(model, key) == data[key]).with_for_update()
    )
    if existing is not None:
        _matching(existing, data, f"{model.__tablename__}/{data[key]}", count)
        count.skipped += 1
        return existing
    entity = model(**data)
    session.add(entity)
    session.flush()  # session factory disables autoflush; resolve identity before dependents
    count.inserted += 1
    return entity


def _require_units(session: Session) -> dict[str, Any]:
    from sqlalchemy import select

    from app.db.models.catalog import Unit, UnitConversion
    from scripts.seed_inventory_units import CONVERSIONS, UNITS

    # Reuse canonical definitions, but never call the helper that reactivates units.
    units = {
        unit.unit_code: unit
        for unit in session.scalars(
            select(Unit)
            .where(Unit.unit_code.in_([row["unit_code"] for row in UNITS]))
            .with_for_update()
        )
    }
    for row in UNITS:
        code = row["unit_code"]
        _require(
            code in units, f"Missing unit {code}; have Person 2 run seed_inventory_units.py first"
        )
        _require(
            units[code].is_active and units[code].dimension == row["dimension"],
            f"Unit {code}: inactive or conflicting dimension; manual review required",
        )
    for from_code, to_code, factor in CONVERSIONS:
        source, target = units[from_code], units[to_code]
        _require(source.dimension == target.dimension, "Canonical conversion dimensions conflict")
        conversion = session.scalar(
            select(UnitConversion)
            .where(
                UnitConversion.from_unit_id == source.unit_id,
                UnitConversion.to_unit_id == target.unit_id,
            )
            .with_for_update()
        )
        _require(
            conversion is not None,
            f"Missing conversion {from_code}->{to_code}; run seed_inventory_units.py first",
        )
        _require(
            conversion.factor == factor,
            f"Conversion {from_code}->{to_code}: conflicting factor; manual review required",
        )
    return units


def seed_demo_menu_recipes(session: Session, counts: dict[str, Counts]) -> dict[str, int]:
    """Insert missing rows or reject conflicts; caller owns the transaction boundary."""
    from sqlalchemy import select

    from app.db.models.catalog import Dish, Ingredient, MenuCategory, RecipeItem, RecipeVersion

    validate_data()
    units = _require_units(session)
    categories = {
        data["category_code"]: _ensure(
            session, MenuCategory, "category_code", data, counts["Categories"]
        )
        for data in CATEGORIES
    }
    ingredients = {}
    for data in INGREDIENTS:
        values = dict(data)
        values["base_unit_id"] = units[values.pop("base_unit_code")].unit_id
        ingredients[data["ingredient_code"]] = _ensure(
            session, Ingredient, "ingredient_code", values, counts["Ingredients"]
        )
    dishes = {}
    for data in DISHES:
        values = dict(data)
        values["category_id"] = categories[values.pop("category_code")].category_id
        dishes[data["dish_code"]] = _ensure(session, Dish, "dish_code", values, counts["Dishes"])
    dish_ids = {code: dish.dish_id for code, dish in dishes.items()}

    for code, dish_id in dish_ids.items():
        versions = list(
            session.scalars(
                select(RecipeVersion).where(RecipeVersion.dish_id == dish_id).with_for_update()
            )
        )
        version = next((row for row in versions if row.version_no == 1), None)
        if any(row.status == "ACTIVE" and row.version_no != 1 for row in versions):
            counts["Recipe versions"].conflict += 1
            raise SeedError(f"{code}: another ACTIVE recipe exists; manual review required")
        if versions and version is None:
            counts["Recipe versions"].conflict += 1
            raise SeedError(f"{code}: existing recipe history; cannot insert demo version 1 safely")
        expected_version = {"dish_id": dish_id, **RECIPE_METADATA}
        is_new = version is None
        if is_new:
            version = RecipeVersion(**expected_version)
            session.add(version)
            session.flush()
            counts["Recipe versions"].inserted += 1
        else:
            _matching(version, expected_version, f"{code}/version 1", counts["Recipe versions"])
            counts["Recipe versions"].skipped += 1

        existing_items = {
            row.ingredient_id: row
            for row in session.scalars(
                select(RecipeItem)
                .where(RecipeItem.recipe_version_id == version.recipe_version_id)
                .with_for_update()
            )
        }
        expected_ids = {
            ingredients[item["ingredient_code"]].ingredient_id for item in RECIPES[code]
        }
        if not is_new and existing_items.keys() != expected_ids:
            counts["Recipe items"].conflict += len(existing_items.keys() ^ expected_ids)
            raise SeedError(f"{code}/version 1: ingredient set changed (missing or extra items)")
        for item in RECIPES[code]:
            ingredient = ingredients[item["ingredient_code"]]
            unit_id = units[item["unit_code"]].unit_id
            _require(
                unit_id == ingredient.base_unit_id, f"{code}: recipe unit differs from base unit"
            )
            values = {
                "recipe_version_id": version.recipe_version_id,
                "ingredient_id": ingredient.ingredient_id,
                "unit_id": unit_id,
                "quantity": item["quantity"],
                # This is a regular NUMERIC(14,3), NOT a generated column in the DDL.
                "base_quantity": item["base_quantity"],
            }
            existing = existing_items.get(ingredient.ingredient_id)
            if existing is not None:
                _matching(
                    existing, values, f"{code}/{item['ingredient_code']}", counts["Recipe items"]
                )
                counts["Recipe items"].skipped += 1
            else:
                session.add(RecipeItem(**values))
                counts["Recipe items"].inserted += 1
        session.flush()
    return dish_ids


def _run_database(mode: str, counts: dict[str, Counts]) -> None:
    # Direct script execution adds backend only here: offline mode imports no app,
    # SQLAlchemy, settings or seed helper and never reads .env.
    backend = str(Path(__file__).resolve().parents[1])
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.db.session import get_session_factory

    with get_session_factory()() as session:
        try:
            seed_demo_menu_recipes(session, counts)
            if mode == "apply":
                session.commit()  # The only commit in this script.
            else:
                session.rollback()
        except BaseException:
            session.rollback()
            raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    modes = parser.add_mutually_exclusive_group()
    for flag, help_text in (
        ("validate-only", "Validate in-code data offline (default)."),
        ("dry-run", "Connect, insert within a transaction, then roll back."),
        ("apply", "Connect and commit the complete seed in one transaction."),
    ):
        modes.add_argument(
            f"--{flag}", dest="mode", action="store_const", const=flag, help=help_text
        )
    parser.set_defaults(mode="validate-only")
    args = parser.parse_args(argv)
    counts = planned_counts()
    database_started = False
    try:
        validate_data()
        if args.mode == "validate-only":
            print("Validation passed: 20 SKUs; no database connection or settings loaded.")
            print(
                "20 pizza_id/type/size triples verified against the documented pizzas.csv mirror."
            )
            print("Toppings remain demo choices; this offline run does not recheck the source CSV.")
            print("Prices: demo VND. Recipe quantities: simulated graduation-project data.")
        else:
            database_started = True
            _run_database(args.mode, counts)
            if args.mode == "dry-run":
                print("DRY RUN rolled back: inserted counts are trial rows, none committed.")
                print("PostgreSQL identity sequences may advance despite rollback.")
            else:
                print("APPLY completed: one transaction committed.")
        return 0
    except SeedError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        if database_started:
            print("Transaction rolled back; inserted counts describe attempted rows only.")
        return 1
    except Exception as error:
        # Driver/settings exceptions may contain credentials, SQL parameters or URLs.
        # Never print the raw exception/traceback, even on a failed connection/commit.
        print(
            f"ERROR: operation failed ({type(error).__name__}); details suppressed.",
            file=sys.stderr,
        )
        print(
            "No successful commit confirmed. Check configuration/connectivity and schema locally."
        )
        print("Inserted counts describe attempted rows only; uncommitted work is rolled back.")
        return 1
    finally:
        print_summary(counts)


if __name__ == "__main__":
    raise SystemExit(main())
