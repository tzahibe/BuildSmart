from fastapi import APIRouter

from app.projects.routes.analytics_routes import router as analytics_router
from app.projects.routes.base_routes import router as base_router
from app.projects.routes.media_routes import router as media_router

router = APIRouter()
router.include_router(base_router)
router.include_router(media_router)
router.include_router(analytics_router)
