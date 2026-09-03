"""
Security middleware — defence-in-depth response headers and the in-process
rate limiter. Both are wired in app.main.create_app().
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.middleware import RateLimitMiddleware, SecurityHeadersMiddleware


@pytest.fixture
def client_headers():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/api/v1/thing")
    def thing():
        return {"ok": True}

    @app.get("/other")
    def other():
        return {"ok": True}

    return TestClient(app)


class TestSecurityHeaders:
    def test_static_headers_present(self, client_headers):
        r = client_headers.get("/api/v1/thing")
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["X-Frame-Options"] == "DENY"
        assert r.headers["Referrer-Policy"] == "no-referrer"
        assert "camera=()" in r.headers["Permissions-Policy"]

    def test_api_responses_are_not_cacheable(self, client_headers):
        assert client_headers.get("/api/v1/thing").headers["Cache-Control"] == "no-store"

    def test_non_api_paths_are_not_forced_no_store(self, client_headers):
        assert "no-store" not in client_headers.get("/other").headers.get("Cache-Control", "")


@pytest.fixture
def client_rl():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, per_minute=3)

    @app.post("/api/v1/defense/verify")
    def verify():
        return {"ok": True}

    @app.get("/api/v1/defense/verify")
    def verify_get():
        return {"ok": True}

    @app.post("/api/v1/health/live")
    def unlimited():
        return {"ok": True}

    return TestClient(app)


class TestRateLimit:
    def test_limits_a_hammered_write_route(self, client_rl):
        codes = [client_rl.post("/api/v1/defense/verify").status_code for _ in range(6)]
        assert codes[:3] == [200, 200, 200]
        assert 429 in codes[3:]
        blocked = client_rl.post("/api/v1/defense/verify")
        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers

    def test_get_requests_are_never_limited(self, client_rl):
        assert all(
            client_rl.get("/api/v1/defense/verify").status_code == 200
            for _ in range(20)
        )

    def test_unlisted_routes_are_never_limited(self, client_rl):
        assert all(
            client_rl.post("/api/v1/health/live").status_code == 200
            for _ in range(20)
        )

    def test_zero_disables_the_limiter(self):
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, per_minute=0)

        @app.post("/api/v1/defense/verify")
        def verify():
            return {"ok": True}

        c = TestClient(app)
        assert all(c.post("/api/v1/defense/verify").status_code == 200 for _ in range(30))
