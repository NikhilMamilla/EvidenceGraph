"""
Tests for the consistent error response format.
"""

from __future__ import annotations

from app.core.errors import ErrorCode, ErrorResponse, error_response


class TestErrorResponseFormat:
    def test_error_response_is_json(self):
        resp = error_response(ErrorCode.INTERNAL_SERVER_ERROR, "test error")
        assert resp.status_code == 500

    def test_error_body_structure(self):
        resp = error_response(ErrorCode.SERVICE_UNAVAILABLE, "Redis down", 503)
        import json

        body = json.loads(resp.body)
        assert "error" in body
        assert body["error"]["code"] == ErrorCode.SERVICE_UNAVAILABLE
        assert body["error"]["message"] == "Redis down"
        assert resp.status_code == 503

    def test_error_schema_validates(self):
        model = ErrorResponse.model_validate(
            {"error": {"code": "NOT_FOUND", "message": "resource missing"}}
        )
        assert model.error.code == "NOT_FOUND"
