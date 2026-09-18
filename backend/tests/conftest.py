import os
import secrets

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings

os.environ["DEBUG"] = "false"
os.environ["DATABASE_URL"] = ""

# Never read the developer's backend/.env, even when pytest runs from backend/.
Settings.model_config["env_file"] = None

from app.main import create_app  # noqa: E402 - disable dotenv before application import

pytest_plugins = ["tests.stock_fixtures"]


@pytest.fixture(autouse=True)
def isolated_inventory_settings(monkeypatch):
    monkeypatch.setenv("INVENTORY_JWT_SECRET_KEY", secrets.token_urlsafe(48))
    monkeypatch.setenv("INVENTORY_JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("INVENTORY_ACCESS_TOKEN_EXPIRE_MINUTES", "480")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client
