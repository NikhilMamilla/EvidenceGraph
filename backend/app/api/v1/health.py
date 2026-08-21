"""
Health endpoints.

GET /api/v1/health/live   — liveness probe (is the process running?)
GET /api/v1/health/ready  — readiness probe (are dependencies reachable?)

Readiness checks both Supabase PostgreSQL and Redis.
Returns 503 with detail if either is unavailable.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.errors import ErrorCode
from app.db.session import check_database_connection, get_database_info
from app.schemas.health import LivenessResponse, ReadinessResponse
from app.services.redis_client import check_redis_connection

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


# ---------------------------------------------------------------------------
# Liveness
# ---------------------------------------------------------------------------
@router.get(
    "/live",
    response_model=LivenessResponse,
    summary="Liveness probe",
    description="Returns 200 if the API process is running.",
)
async def liveness() -> LivenessResponse:
    from app.core.config import get_settings

    settings = get_settings()
    return LivenessResponse(status="ok", service=settings.app_name)


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------
@router.get(
    "/ready",
    summary="Readiness probe",
    description=(
        "Returns 200 only when both Supabase PostgreSQL and Redis are reachable. "
        "Returns 503 if either dependency is unavailable."
    ),
)
async def readiness() -> JSONResponse:
    db_ok = check_database_connection()
    redis_ok = check_redis_connection()

    db_status = "connected" if db_ok else "unavailable"
    redis_status = "connected" if redis_ok else "unavailable"

    if db_ok and redis_ok:
        body = ReadinessResponse(
            status="ready",
            database=db_status,
            redis=redis_status,
        )
        return JSONResponse(status_code=200, content=body.model_dump())

    logger.warning(
        "Readiness check failed",
        extra={"database": db_status, "redis": redis_status},
    )

    failing = []
    if not db_ok:
        failing.append("Supabase PostgreSQL")
    if not redis_ok:
        failing.append("Redis")

    return JSONResponse(
        status_code=503,
        content={
            "status": "not_ready",
            "database": db_status,
            "redis": redis_status,
            "error": {
                "code": ErrorCode.SERVICE_UNAVAILABLE,
                "message": f"Unavailable: {', '.join(failing)}",
            },
        },
    )


# ---------------------------------------------------------------------------
# Database verification — confirms we are connected to the correct Supabase
# project. Returns safe metadata only. No credentials exposed.
# ---------------------------------------------------------------------------
@router.get(
    "/db-info",
    summary="Database verification",
    description=(
        "Returns safe metadata about the connected PostgreSQL instance. "
        "Use this to confirm the backend is connected to the intended "
        "Supabase project."
    ),
)
async def db_info() -> JSONResponse:
    try:
        info = get_database_info()
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "database_info": info},
        )
    except Exception as exc:
        logger.warning("DB info check failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "error": {
                    "code": ErrorCode.SERVICE_UNAVAILABLE,
                    "message": "Could not retrieve database info",
                },
            },
        )
