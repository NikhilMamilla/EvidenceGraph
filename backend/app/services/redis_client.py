"""
Redis client initialisation and connectivity utilities.

Phase 1 responsibilities:
  - Create a single Redis connection pool shared across the application.
  - Expose a health-check function used by /health/ready.
  - Provide clean shutdown (called from application lifespan).

No business logic (caching, queues, pub/sub) is implemented here — those
belong to later phases.
"""

from __future__ import annotations

import logging

import redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level client — lazily initialised
# ---------------------------------------------------------------------------
_redis_client: redis.Redis | None = None  # type: ignore[type-arg]


def get_redis_client() -> redis.Redis:  # type: ignore[type-arg]
    """Return the shared Redis client, creating it on first call."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
            retry_on_timeout=False,
        )
        logger.info("Redis client created")
    return _redis_client


def check_redis_connection() -> bool:
    """
    Return True if Redis is reachable via PING, False otherwise.
    Does NOT raise — callers handle the boolean.
    """
    try:
        client = get_redis_client()
        response = client.ping()
        return response is True
    except Exception as exc:
        logger.warning("Redis connectivity check failed: %s", exc)
        return False


def close_redis_connection() -> None:
    """Close the Redis connection pool during application shutdown."""
    global _redis_client
    if _redis_client is not None:
        try:
            _redis_client.close()
            logger.info("Redis connection closed")
        except Exception as exc:
            logger.warning("Error closing Redis connection: %s", exc)
        finally:
            _redis_client = None
