"""
Pytest configuration and shared fixtures.

All mocking of infrastructure dependencies (DB, Redis) happens HERE inside
test isolation — never in production application code.

Run tests from inside the backend virtual environment:
    .venv\\Scripts\\activate
    python -m pytest tests/ -v
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Set test environment variables BEFORE importing the app so that
# pydantic-settings reads them and the Settings object is valid.
# ---------------------------------------------------------------------------
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/evidencegraph_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")
os.environ.setdefault("LOG_LEVEL", "WARNING")


# ---------------------------------------------------------------------------
# Shared app fixture — created once per test session.
# The lifespan (startup) calls get_engine() which we patch to avoid
# requiring a real PostgreSQL connection during unit tests.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def app():
    """Return the FastAPI application instance with DB engine patched."""
    from app.core.config import get_settings

    get_settings.cache_clear()

    # Patch get_engine so the lifespan startup doesn't try to connect to a
    # real database.  All actual connectivity checks are patched per-fixture.
    with patch("app.db.session.get_engine", return_value=MagicMock()):
        from app.main import create_app

        return create_app()


@pytest.fixture(scope="session")
def client_healthy(app):
    """
    Test client where both DB and Redis report healthy.
    """
    with (
        patch("app.api.v1.health.check_database_connection", return_value=True),
        patch("app.api.v1.health.check_redis_connection", return_value=True),
    ):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


@pytest.fixture(scope="function")
def client_db_down(app):
    """Test client where DB is unavailable."""
    with (
        patch("app.api.v1.health.check_database_connection", return_value=False),
        patch("app.api.v1.health.check_redis_connection", return_value=True),
    ):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


@pytest.fixture(scope="function")
def client_redis_down(app):
    """Test client where Redis is unavailable."""
    with (
        patch("app.api.v1.health.check_database_connection", return_value=True),
        patch("app.api.v1.health.check_redis_connection", return_value=False),
    ):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


@pytest.fixture(scope="function")
def client_both_down(app):
    """Test client where both DB and Redis are unavailable."""
    with (
        patch("app.api.v1.health.check_database_connection", return_value=False),
        patch("app.api.v1.health.check_redis_connection", return_value=False),
    ):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
