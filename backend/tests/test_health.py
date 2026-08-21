"""
Tests for /api/v1/health/live and /api/v1/health/ready endpoints.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Liveness
# ---------------------------------------------------------------------------
class TestLiveness:
    def test_live_returns_200(self, client_healthy):
        resp = client_healthy.get("/api/v1/health/live")
        assert resp.status_code == 200

    def test_live_response_schema(self, client_healthy):
        resp = client_healthy.get("/api/v1/health/live")
        body = resp.json()
        assert body["status"] == "ok"
        assert "service" in body
        assert body["service"] == "evidencegraph-api"

    def test_live_has_request_id_header(self, client_healthy):
        resp = client_healthy.get("/api/v1/health/live")
        assert "x-request-id" in resp.headers

    def test_live_request_id_is_uuid_format(self, client_healthy):
        import re
        resp = client_healthy.get("/api/v1/health/live")
        rid = resp.headers.get("x-request-id", "")
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            re.IGNORECASE,
        )
        assert uuid_pattern.match(rid), f"Not a UUID: {rid}"


# ---------------------------------------------------------------------------
# Readiness — healthy state
# ---------------------------------------------------------------------------
class TestReadinessHealthy:
    def test_ready_returns_200_when_both_up(self, client_healthy):
        resp = client_healthy.get("/api/v1/health/ready")
        assert resp.status_code == 200

    def test_ready_schema_when_healthy(self, client_healthy):
        resp = client_healthy.get("/api/v1/health/ready")
        body = resp.json()
        assert body["status"] == "ready"
        assert body["database"] == "connected"
        assert body["redis"] == "connected"


# ---------------------------------------------------------------------------
# Readiness — degraded states
# ---------------------------------------------------------------------------
class TestReadinessDegraded:
    def test_ready_503_when_db_down(self, client_db_down):
        resp = client_db_down.get("/api/v1/health/ready")
        assert resp.status_code == 503

    def test_ready_db_status_unavailable_when_db_down(self, client_db_down):
        body = client_db_down.get("/api/v1/health/ready").json()
        assert body["database"] == "unavailable"
        assert body["redis"] == "connected"

    def test_ready_503_when_redis_down(self, client_redis_down):
        resp = client_redis_down.get("/api/v1/health/ready")
        assert resp.status_code == 503

    def test_ready_redis_status_unavailable_when_redis_down(self, client_redis_down):
        body = client_redis_down.get("/api/v1/health/ready").json()
        assert body["redis"] == "unavailable"
        assert body["database"] == "connected"

    def test_ready_503_when_both_down(self, client_both_down):
        resp = client_both_down.get("/api/v1/health/ready")
        assert resp.status_code == 503

    def test_ready_error_code_when_both_down(self, client_both_down):
        body = client_both_down.get("/api/v1/health/ready").json()
        assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
        assert "PostgreSQL" in body["error"]["message"]
        assert "Redis" in body["error"]["message"]


# ---------------------------------------------------------------------------
# Correlation ID propagation
# ---------------------------------------------------------------------------
class TestCorrelationID:
    def test_provided_request_id_is_echoed(self, client_healthy):
        custom_id = "test-correlation-id-1234"
        resp = client_healthy.get(
            "/api/v1/health/live",
            headers={"X-Request-ID": custom_id},
        )
        assert resp.headers.get("x-request-id") == custom_id

    def test_auto_generated_request_id_is_present(self, client_healthy):
        resp = client_healthy.get("/api/v1/health/live")
        rid = resp.headers.get("x-request-id", "")
        assert rid != ""
