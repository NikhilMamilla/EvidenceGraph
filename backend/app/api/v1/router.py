"""
API v1 router — aggregates all v1 route modules.
"""

from fastapi import APIRouter

from app.api.v1.health import router as health_router

router = APIRouter(prefix="/api/v1")
router.include_router(health_router, prefix="/health")
