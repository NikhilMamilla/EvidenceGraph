"""
SQLAlchemy session management — Supabase PostgreSQL backend.

Connection notes:
  - Uses the Supabase direct connection (port 5432) with sslmode=require.
  - Pool is intentionally conservative for the Supabase Free Tier
    (max 60 connections shared across all clients).
  - pool_pre_ping=True ensures stale connections are recycled automatically.

Business models (Payment, Evidence, etc.) belong to later phases.
This module only establishes connectivity and exposes health/verification helpers.
"""

from __future__ import annotations

import logging
from typing import Any, Generator

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
            pool_pre_ping=True,   # recycle stale connections automatically
            pool_size=3,          # conservative: Supabase Free Tier has 60 max
            max_overflow=5,       # allow short bursts up to 8 total
            pool_recycle=300,     # recycle connections every 5 minutes
            echo=False,
        )
        logger.info("SQLAlchemy engine created (Supabase)")
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
    Return True if Supabase PostgreSQL is reachable, False otherwise.
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


# ---------------------------------------------------------------------------
# Verification — confirms we are connected to the correct Supabase project
# Used by the /health/ready endpoint's detailed response and startup logging.
# Returns safe metadata only — no credentials exposed.
# ---------------------------------------------------------------------------
def get_database_info() -> dict[str, Any]:
    """
    Return safe metadata about the connected database.
    Raises on failure — callers should catch.
    Uses only standard PostgreSQL functions compatible with Supabase Session Pooler.
    """
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT version(), current_database(), current_user"
            )
        ).fetchone()
    if row is None:
        return {}
    version_str = str(row[0])
    # Extract just "PostgreSQL X.Y" from the full version string
    pg_version = " ".join(version_str.split()[:2])
    return {
        "pg_version": pg_version,
        "database": row[1],
        "user": row[2],
        "provider": "supabase",
    }
