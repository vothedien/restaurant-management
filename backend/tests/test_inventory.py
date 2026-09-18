from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.db.models.catalog import Ingredient, Unit, UnitConversion
from app.db.session import get_db
from app.modules.inventory import router as inventory_router
from app.modules.inventory.schemas import (
    IngredientCreate,
    UnitConversionCreate,
    UnitCreate,
)
from app.modules.inventory.service import InventoryService
from app.modules.inventory_auth.dependencies import get_current_inventory_user
from tests.inventory_auth_fixtures import unit_test_principal


class FakeSession:
    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def refresh(self, _: object) -> None:
        pass

    def delete(self, _: object) -> None:
        pass


class FakeInventoryRepository:
    def __init__(self) -> None:
        self.units: dict[int, Unit] = {}
        self.conversions: dict[int, UnitConversion] = {}
        self.ingredients: dict[int, Ingredient] = {}
        self._next_unit_id = 1
        self._next_conversion_id = 1
        self._next_ingredient_id = 1

    def get_unit(self, _: FakeSession, unit_id: int) -> Unit | None:
        return self.units.get(unit_id)

    def get_unit_by_code(self, _: FakeSession, unit_code: str) -> Unit | None:
        return next((unit for unit in self.units.values() if unit.unit_code == unit_code), None)

    def get_conversion(self, _: FakeSession, conversion_id: int) -> UnitConversion | None:
        return self.conversions.get(conversion_id)

    def get_conversion_by_pair(
        self,
        _: FakeSession,
        *,
        from_unit_id: int,
        to_unit_id: int,
        exclude_conversion_id: int | None = None,
    ) -> UnitConversion | None:
        return next(
            (
                conversion
                for conversion in self.conversions.values()
                if conversion.from_unit_id == from_unit_id
                and conversion.to_unit_id == to_unit_id
                and conversion.conversion_id != exclude_conversion_id
            ),
            None,
        )

    def get_ingredient(self, _: FakeSession, ingredient_id: int) -> Ingredient | None:
        return self.ingredients.get(ingredient_id)

    def get_ingredient_by_code(self, _: FakeSession, ingredient_code: str) -> Ingredient | None:
        return next(
            (
                ingredient
                for ingredient in self.ingredients.values()
                if ingredient.ingredient_code == ingredient_code
            ),
            None,
        )

    def add(self, _: FakeSession, entity: Unit | UnitConversion | Ingredient) -> None:
        if isinstance(entity, Unit):
            entity.unit_id = self._next_unit_id
            self.units[entity.unit_id] = entity
            self._next_unit_id += 1
        elif isinstance(entity, UnitConversion):
            entity.conversion_id = self._next_conversion_id
            entity.from_unit = self.units[entity.from_unit_id]
            entity.to_unit = self.units[entity.to_unit_id]
            self.conversions[entity.conversion_id] = entity
            self._next_conversion_id += 1
        else:
            entity.ingredient_id = self._next_ingredient_id
            entity.base_unit = self.units[entity.base_unit_id]
            entity.created_at = datetime.now(UTC)
            entity.updated_at = entity.created_at
            self.ingredients[entity.ingredient_id] = entity
            self._next_ingredient_id += 1


@pytest.fixture
def repository() -> FakeInventoryRepository:
    return FakeInventoryRepository()


@pytest.fixture
def service(repository: FakeInventoryRepository) -> InventoryService:
    return InventoryService(repository)  # type: ignore[arg-type]


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def inventory_client(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    service: InventoryService,
    session: FakeSession,
) -> TestClient:
    def override_get_db() -> FakeSession:
        return session

    monkeypatch.setattr(inventory_router, "service", service)
    client.app.dependency_overrides[get_db] = override_get_db
    client.app.dependency_overrides[get_current_inventory_user] = unit_test_principal
    yield client
    client.app.dependency_overrides.clear()


def add_unit(repository: FakeInventoryRepository, unit_id: int, code: str, dimension: str) -> Unit:
    unit = Unit(
        unit_id=unit_id,
        unit_code=code,
        unit_name=code,
        dimension=dimension,
        is_active=True,
    )
    repository.units[unit_id] = unit
    repository._next_unit_id = max(repository._next_unit_id, unit_id + 1)
    return unit


def test_creates_unit_and_normalizes_code(
    service: InventoryService, session: FakeSession, repository: FakeInventoryRepository
) -> None:
    unit = service.create_unit(
        session, UnitCreate(unit_code=" kg ", unit_name="Kilogram", dimension="mass")
    )

    assert unit.unit_code == "KG"
    assert repository.units[unit.unit_id].dimension == "MASS"


def test_rejects_duplicate_unit_code(
    service: InventoryService, session: FakeSession, repository: FakeInventoryRepository
) -> None:
    add_unit(repository, 1, "G", "MASS")

    with pytest.raises(ConflictError, match="Unit code already exists"):
        service.create_unit(
            session, UnitCreate(unit_code=" g ", unit_name="Gram", dimension="MASS")
        )


def test_rejects_invalid_unit_dimension() -> None:
    with pytest.raises(ValidationError):
        UnitCreate(unit_code="G", unit_name="Gram", dimension="WEIGHT")


def test_creates_valid_conversion(
    service: InventoryService, session: FakeSession, repository: FakeInventoryRepository
) -> None:
    add_unit(repository, 1, "KG", "MASS")
    add_unit(repository, 2, "G", "MASS")

    conversion = service.create_conversion(
        session, UnitConversionCreate(from_unit_id=1, to_unit_id=2, factor=Decimal("1000"))
    )

    assert conversion.factor == Decimal("1000")
    assert conversion.from_unit.unit_code == "KG"
    assert conversion.to_unit.unit_code == "G"


def test_rejects_conversion_between_different_dimensions(
    service: InventoryService, session: FakeSession, repository: FakeInventoryRepository
) -> None:
    add_unit(repository, 1, "KG", "MASS")
    add_unit(repository, 2, "L", "VOLUME")

    with pytest.raises(BusinessRuleError, match="matching dimensions"):
        service.create_conversion(
            session, UnitConversionCreate(from_unit_id=1, to_unit_id=2, factor=Decimal("1"))
        )


@pytest.mark.parametrize("factor", ["0", "-1"])
def test_rejects_non_positive_conversion_factor(factor: str) -> None:
    with pytest.raises(ValidationError):
        UnitConversionCreate(from_unit_id=1, to_unit_id=2, factor=Decimal(factor))


def test_creates_ingredient_with_active_base_unit(
    service: InventoryService, session: FakeSession, repository: FakeInventoryRepository
) -> None:
    add_unit(repository, 1, "G", "MASS")

    ingredient = service.create_ingredient(
        session,
        IngredientCreate(
            ingredient_code=" tomato ",
            ingredient_name="Tomato",
            base_unit_id=1,
            minimum_stock_qty=Decimal("1"),
        ),
    )

    assert ingredient.ingredient_code == "TOMATO"
    assert ingredient.base_unit.unit_code == "G"


def test_rejects_ingredient_with_missing_base_unit(
    service: InventoryService, session: FakeSession
) -> None:
    with pytest.raises(NotFoundError, match="Base unit not found"):
        service.create_ingredient(
            session,
            IngredientCreate(
                ingredient_code="TOMATO",
                ingredient_name="Tomato",
                base_unit_id=999,
            ),
        )


def test_rejects_negative_minimum_stock() -> None:
    with pytest.raises(ValidationError):
        IngredientCreate(
            ingredient_code="TOMATO",
            ingredient_name="Tomato",
            base_unit_id=1,
            minimum_stock_qty=Decimal("-0.001"),
        )


def test_returns_not_found_for_missing_resource(
    service: InventoryService, session: FakeSession
) -> None:
    with pytest.raises(NotFoundError, match="Ingredient not found"):
        service.get_ingredient(session, 999)


def test_api_creates_unit_with_standard_response(inventory_client: TestClient) -> None:
    response = inventory_client.post(
        "/api/v1/inventory/units",
        json={"unit_code": " kg ", "unit_name": "Kilogram", "dimension": "mass"},
    )

    assert response.status_code == 201
    assert response.json() == {
        "success": True,
        "message": "Unit created",
        "data": {
            "unit_id": 1,
            "unit_code": "KG",
            "unit_name": "Kilogram",
            "dimension": "MASS",
            "is_active": True,
        },
    }


def test_api_returns_standard_404(inventory_client: TestClient) -> None:
    response = inventory_client.get("/api/v1/inventory/ingredients/999")

    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "message": "Ingredient not found",
        "data": None,
    }


def test_api_returns_standard_422_for_invalid_input(inventory_client: TestClient) -> None:
    response = inventory_client.post(
        "/api/v1/inventory/unit-conversions",
        json={"from_unit_id": 1, "to_unit_id": 2, "factor": 0},
    )

    assert response.status_code == 422
    assert response.json() == {
        "success": False,
        "message": "Request validation failed",
        "data": None,
    }
