"""
Request middleware for EvidenceGraph API.

Responsibilities:
  1. Assign / propagate a correlation ID (X-Request-ID) per request.
  2. Emit a structured access log after each response.

The correlation ID is stored in a ContextVar so it is visible to all
log statements produced during the same async request without being
threaded through function signatures.
"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import generate_request_id, get_request_id, set_request_id

logger = logging.getLogger(__name__)

_REQUEST_ID_HEADER = "X-Request-ID"


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that:
    - Reads X-Request-ID from incoming request headers (if provided by client/proxy).
    - Generates a new UUID v4 request ID if none is present.
    - Stores the ID in the async ContextVar so all downstream code can read it.
    - Injects X-Request-ID into the outgoing response headers.
    - Emits a structured access log line after the response is sent.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Honour client-provided request ID (e.g. from an API gateway or test)
        request_id = (
            request.headers.get(_REQUEST_ID_HEADER) or generate_request_id()
        )
        set_request_id(request_id)

        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        # Propagate request ID back to the caller
        response.headers[_REQUEST_ID_HEADER] = request_id

        logger.info(
            "request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
        return response
