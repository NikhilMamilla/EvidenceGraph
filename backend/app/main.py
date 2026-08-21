"""
EvidenceGraph — FastAPI application entry point.

Supabase Migration: backend now connects to Supabase PostgreSQL via SSL.
Phase 1 foundation infrastructure remains unchanged.
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

configure_logging()
logger = logging.getLogger(__name__)


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

    # Warm up DB engine and verify we're connected to Supabase
    try:
        from app.db.session import get_database_info, get_engine

        get_engine()
        db_info = get_database_info()
        logger.info(
            "Supabase PostgreSQL connected",
            extra={
                "pg_version": db_info.get("pg_version"),
                "database": db_info.get("database"),
                "user": db_info.get("user"),
                # host is logged for verification — not a secret
                "host": db_info.get("host"),
            },
        )
    except Exception as exc:
        logger.warning("DB startup verification skipped: %s", exc)

    yield

    logger.info("Shutting down EvidenceGraph API")
    close_redis_connection()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="EvidenceGraph API",
        description=(
            "Real-Time Payment-Risk Evidence Intelligence Platform. "
            "Database: Supabase PostgreSQL (Session Pooler, SSL)."
        ),
        version="0.1.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    app.add_middleware(CorrelationIDMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.add_exception_handler(Exception, unhandled_exception_handler)  # type: ignore[arg-type]
    app.include_router(v1_router)

    return app


app = create_app()
