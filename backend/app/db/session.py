"""
SQLAlchemy async-compatible session management.

Phase 1 uses a synchronous psycopg2 driver (simpler, no extra deps).
The session factory is created once at import time and reused across requests.

Business models (Payment, Evidence, etc.) belong to later phases.
This module only establishes connectivity.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Declarative base — shared by all future models
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Engine & session factory — created lazily on first access
# ---------------------------------------------------------------------------
_engine = None
_SessionLocal = None


def get_engine():  # type: ignore[return]
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,       # verify connections before use
            pool_size=5,
            max_overflow=10,
            echo=False,               # set True for SQL debug logging
        )
        logger.info("SQLAlchemy engine created")
    return _engine


def get_session_factory() -> sessionmaker:  # type: ignore[type-arg]
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _SessionLocal


# ---------------------------------------------------------------------------
# Dependency — FastAPI route dependency injection
# ---------------------------------------------------------------------------
def get_db() -> Generator[Session, None, None]:
    """Yield a database session and ensure it is closed after use."""
    SessionLocal = get_session_factory()
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Connectivity probe — used by /health/ready
# ---------------------------------------------------------------------------
def check_database_connection() -> bool:
    """
    Return True if PostgreSQL is reachable, False otherwise.
    Does NOT raise — callers handle the boolean.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("Database connectivity check failed: %s", exc)
        return False
