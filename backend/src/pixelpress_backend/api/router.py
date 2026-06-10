from fastapi import APIRouter

from pixelpress_backend.api.routes import health, layouts, operations


api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(layouts.router)
api_router.include_router(operations.router)
