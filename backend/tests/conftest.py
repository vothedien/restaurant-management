import os

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings

os.environ["DEBUG"] = "false"
os.environ["DATABASE_URL"] = ""

# Never read the developer's backend/.env, even when pytest runs from backend/.
Settings.model_config["env_file"] = None

from app.main import create_app  # noqa: E402 - disable dotenv before application import

pytest_plugins = ["tests.stock_fixtures"]


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client
