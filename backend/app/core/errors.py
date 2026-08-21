"""
Consistent error response schema for the EvidenceGraph API.

All API errors are returned as:
{
    "error": {
        "code": "ERROR_CODE",
        "message": "Human-readable description"
    }
}

Internal details (stack traces, DB credentials, env vars) are NEVER exposed
to API clients.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schema for a single error body
# ---------------------------------------------------------------------------
class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ---------------------------------------------------------------------------
# Known error codes
# ---------------------------------------------------------------------------
class ErrorCode:
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    BAD_REQUEST = "BAD_REQUEST"


# ---------------------------------------------------------------------------
# Helper — build a JSONResponse in the standard format
# ---------------------------------------------------------------------------
def error_response(
    code: str,
    message: str,
    status_code: int = 500,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message))
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(),
    )


# ---------------------------------------------------------------------------
# FastAPI exception handlers
# ---------------------------------------------------------------------------
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch-all — log the real error internally, return safe generic response."""
    from app.core.logging import get_request_id

    logger.exception(
        "Unhandled exception",
        extra={
            "request_id": get_request_id(),
            "path": request.url.path,
            "method": request.method,
        },
    )
    return error_response(
        code=ErrorCode.INTERNAL_SERVER_ERROR,
        message="An unexpected error occurred. Please try again later.",
        status_code=500,
    )
