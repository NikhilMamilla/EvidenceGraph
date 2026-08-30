"""
Application configuration.

All settings are loaded from environment variables (or a .env file via
pydantic-settings).  No secrets are hardcoded.  Razorpay credentials are
optional for Phase 1 and will be validated in a later phase.
"""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The .env file lives at the project root (one level above backend/)
# Works whether uvicorn is run from backend/ or from the project root.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _PROJECT_ROOT / ".env"


class AppEnv(str, Enum):
    development = "development"
    staging = "staging"
    production = "production"
    test = "test"


class LogLevel(str, Enum):
    debug = "DEBUG"
    info = "INFO"
    warning = "WARNING"
    error = "ERROR"
    critical = "CRITICAL"


class Settings(BaseSettings):
    """
    Central settings object.

    Required infrastructure variables must be present at startup.
    Razorpay variables are optional in Phase 1.
    """

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    app_env: AppEnv = AppEnv.development
    app_name: str = "evidencegraph-api"
    backend_port: int = 8000
    frontend_port: int = 5173

    # ------------------------------------------------------------------
    # Database — required
    # ------------------------------------------------------------------
    database_url: str

    # ------------------------------------------------------------------
    # Redis — required
    # ------------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    log_level: LogLevel = LogLevel.info

    # ------------------------------------------------------------------
    # Razorpay — OPTIONAL in Phase 1, REQUIRED in Phase 2
    # ------------------------------------------------------------------
    razorpay_mode: str = "test"   # "test" or "live"
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # ------------------------------------------------------------------
    # Audit-trace administration — Phase 10
    # Restricted surfaces (full traces, verification, replay) require this
    # key via the X-API-Key header. Empty means restricted endpoints fail
    # closed (503).
    # ------------------------------------------------------------------
    admin_api_key: str = ""

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS origins as a parsed list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == AppEnv.production

    @property
    def razorpay_configured(self) -> bool:
        """True only when all three Razorpay credentials are present."""
        return bool(
            self.razorpay_key_id
            and self.razorpay_key_secret
            and self.razorpay_webhook_secret
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v:
            raise ValueError("DATABASE_URL must not be empty")
        if not v.startswith("postgresql://") and not v.startswith("postgresql+"):
            raise ValueError(
                "DATABASE_URL must be a PostgreSQL connection string "
                "(postgresql://...)"
            )
        return v

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, v: str) -> str:
        if not v:
            raise ValueError("REDIS_URL must not be empty")
        if not v.startswith("redis://") and not v.startswith("rediss://"):
            raise ValueError("REDIS_URL must start with redis:// or rediss://")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.  Call this everywhere."""
    return Settings()  # type: ignore[call-arg]
