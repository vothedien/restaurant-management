"""Isolated UI demo server. All writes are to disposable SQLite memory only.

Run from repository root: python frontend/e2e/demo_api.py
Uses the existing backend's test fixtures, routes, services and ORM.
No dotenv, Neon, migration or persistent database access is permitted here.
"""
import os
import secrets
import sys
from pathlib import Path
from threading import Lock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
os.environ["DATABASE_URL"] = ""
os.environ["DEBUG"] = "false"
os.environ["FRONTEND_URL"] = "http://localhost:5173"
os.environ["INVENTORY_JWT_SECRET_KEY"] = secrets.token_urlsafe(48)
os.environ["INVENTORY_JWT_ALGORITHM"] = "HS256"
os.environ["INVENTORY_ACCESS_TOKEN_EXPIRE_MINUTES"] = "480"

from app.core.config import Settings  # noqa: E402

Settings.model_config["env_file"] = None

import uvicorn  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from app.main import create_app  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.db.models.catalog import Dish, MenuCategory  # noqa: E402
from tests.stock_fixtures import stock_engine, stock_session  # noqa: E402

engine_fixture = stock_engine.__wrapped__()
engine = next(engine_fixture)
seed_fixture = stock_session.__wrapped__(engine)
seed = next(seed_fixture)
seed.add(MenuCategory(category_id=1, category_code="TEST", category_name="Thực đơn thử nghiệm"))
seed.flush()
seed.add(Dish(dish_id=1, dish_code="TEST-DISH", dish_name="Món thử nghiệm", category_id=1, selling_price=100000))
seed.commit()
seed.close()
lock = Lock()


def local_session():
    # StaticPool has one SQLite connection; serialize requests in this demo.
    with lock:
        with Session(engine, autoflush=False) as session:
            yield session


app = create_app()
app.dependency_overrides[get_db] = local_session


@app.get("/__test__/environment")
def environment():
    return {"environment": "inventory-ui-sqlite-memory", "persistent": False, "auth": "inventory-real-backend"}


if __name__ == "__main__":
    try:
        uvicorn.run(app, host="127.0.0.1", port=8011, log_level="warning")
    finally:
        seed_fixture.close()
        engine_fixture.close()
