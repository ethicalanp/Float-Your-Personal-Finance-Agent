from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.plan import router as plan_router
from app.api.v1.protect import router as protect_router

api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(plan_router)
api_router.include_router(protect_router)
