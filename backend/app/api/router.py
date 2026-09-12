from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.catalog.router import router as catalog_router
from app.modules.forecasting.router import router as forecasting_router
from app.modules.inventory.router import router as inventory_router
from app.modules.purchasing.router import router as purchasing_router
from app.modules.recipes.router import router as recipes_router
from app.modules.sales.router import router as sales_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(catalog_router)
api_router.include_router(sales_router)
api_router.include_router(inventory_router)
api_router.include_router(recipes_router)
api_router.include_router(purchasing_router)
api_router.include_router(forecasting_router)
