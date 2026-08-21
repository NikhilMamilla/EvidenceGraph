"""
EvidenceGraph — FastAPI application entry point.

Phase 1: Production Foundation
  - Structured logging
  - Correlation ID middleware
  - CORS (read from environment — never wildcard)
  - Health endpoints: /api/v1/health/live, /api/v1/health/ready
  - Consistent error format
  - Clean startup / shutdown lifecycle
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.core.errors import unhandled_exception_handler
from app.core.logging import configure_logging
from app.core.middleware import CorrelationIDMiddleware
from app.services.redis_client import close_redis_connection

# Configure structured logging before anything else touches the logger
configure_logging()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Application lifespan — startup / shutdown logic
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info(
        "Starting EvidenceGraph API",
        extra={
            "app_name": settings.app_name,
            "environment": settings.app_env.value,
            "razorpay_configured": settings.razorpay_configured,
        },
    )

    # Pre-warm the DB engine — validates DATABASE_URL on startup.
    # Wrapped in try/except so the app can still start in test environments
    # where the engine is mocked or DB is not yet available.
    try:
        from app.db.session import get_engine

        get_engine()
    except Exception as exc:
        logger.warning("DB engine warm-up skipped: %s", exc)

    yield  # ← application runs here

    logger.info("Shutting down EvidenceGraph API")
    close_redis_connection()


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="EvidenceGraph API",
        description=(
            "Real-Time Payment-Risk Evidence Intelligence Platform. "
            "Phase 1: Production Foundation."
        ),
        version="0.1.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # Correlation ID / structured access logging
    # Must be added BEFORE CORSMiddleware so it wraps the full request.
    # ------------------------------------------------------------------
    app.add_middleware(CorrelationIDMiddleware)

    # ------------------------------------------------------------------
    # CORS — origins read from environment; never wildcard
    # ------------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Exception handlers
    # ------------------------------------------------------------------
    app.add_exception_handler(Exception, unhandled_exception_handler)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Routers
    # ------------------------------------------------------------------
    app.include_router(v1_router)

    return app


app = create_app()
