from fastapi.testclient import TestClient
from pytest import MonkeyPatch

import app.main as main_module
from app.core.exceptions import DatabaseNotConfiguredError


def test_health_is_independent_from_database(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Application is healthy",
        "data": {"status": "ok"},
    }


def test_database_health_reports_missing_configuration_safely(
    client: TestClient, monkeypatch: MonkeyPatch
) -> None:
    def raise_database_not_configured() -> None:
        raise DatabaseNotConfiguredError("DATABASE_URL is not configured.")

    monkeypatch.setattr(main_module, "get_engine", raise_database_not_configured)

    response = client.get("/health/database")
    assert response.status_code == 503
    assert response.json() == {
        "success": False,
        "message": "Database is not configured",
        "data": None,
    }
