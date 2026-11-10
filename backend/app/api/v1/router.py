from fastapi import APIRouter

from app.api.v1 import health, repositories, saved

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(repositories.router)
api_router.include_router(saved.router)
