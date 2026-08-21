"""
Tests for configuration validation.

Verify that:
- Valid config loads correctly.
- Invalid DATABASE_URL is rejected.
- Invalid REDIS_URL is rejected.
- Razorpay credentials are optional (empty is accepted).
- CORS origins list parses correctly.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestConfigValidation:
    def _make_settings(self, **overrides):
        """Create a Settings instance with known-good defaults, overriding fields."""
        from app.core.config import Settings

        base = dict(
            app_env="test",
            database_url="postgresql://postgres:postgres@localhost:5432/test",
            redis_url="redis://localhost:6379/0",
            cors_origins="http://localhost:5173",
        )
        base.update(overrides)
        return Settings(**base)  # type: ignore[call-arg]

    def test_valid_config_loads(self):
        s = self._make_settings()
        assert s.database_url.startswith("postgresql://")
        assert s.redis_url.startswith("redis://")

    def test_invalid_database_url_raises(self):
        with pytest.raises(ValidationError, match="PostgreSQL"):
            self._make_settings(database_url="mysql://user:pass@host/db")

    def test_empty_database_url_raises(self):
        with pytest.raises(ValidationError):
            self._make_settings(database_url="")

    def test_invalid_redis_url_raises(self):
        with pytest.raises(ValidationError, match="redis://"):
            self._make_settings(redis_url="memcached://localhost:11211")

    def test_razorpay_optional(self):
        """Razorpay credentials empty — must not raise."""
        s = self._make_settings(
            razorpay_key_id="",
            razorpay_key_secret="",
            razorpay_webhook_secret="",
        )
        assert s.razorpay_configured is False

    def test_razorpay_configured_when_all_set(self):
        s = self._make_settings(
            razorpay_key_id="rzp_test_key",
            razorpay_key_secret="secret",
            razorpay_webhook_secret="whsecret",
        )
        assert s.razorpay_configured is True

    def test_cors_origins_parsed_to_list(self):
        s = self._make_settings(
            cors_origins="http://localhost:5173,http://localhost:3000"
        )
        origins = s.cors_origins_list
        assert "http://localhost:5173" in origins
        assert "http://localhost:3000" in origins
        assert len(origins) == 2

    def test_cors_origins_strips_whitespace(self):
        s = self._make_settings(
            cors_origins="http://localhost:5173 , http://localhost:3000 "
        )
        assert all(not o.startswith(" ") for o in s.cors_origins_list)
