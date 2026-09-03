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


# ===========================================================================
# Security headers
# ===========================================================================
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add defence-in-depth response headers.

    The frontend is served by nginx (which sets its own headers); this covers
    direct access to the API on :8000 and any deployment without a proxy.
    """

    _STATIC = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-site",
    }

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        for k, v in self._STATIC.items():
            response.headers.setdefault(k, v)
        # API JSON is per-request state — never let a shared cache keep it.
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


# ===========================================================================
# In-process rate limiting (token bucket, per client IP)
# ===========================================================================
import threading
from collections import defaultdict


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window limiter for mutating / expensive routes.

    Deliberately simple and dependency-free: a per-IP counter reset every 60s.
    Good enough to blunt a scripted hammer on a demo box; a real deployment
    would put this at the edge (nginx / API gateway). GET requests and the
    health probes are never limited.
    """

    _LIMITED_PREFIXES = (
        "/api/v1/webhooks",
        "/api/v1/defense/evaluation/run",
        "/api/v1/defense/evaluation/seed",
        "/api/v1/defense/evaluation/freeze",
        "/api/v1/defense/ai/evaluate",
        "/api/v1/defense/verify",
    )

    def __init__(self, app, per_minute: int = 120) -> None:
        super().__init__(app)
        self._per_minute = per_minute
        self._lock = threading.Lock()
        self._window_start = time.time()
        self._counts: dict[str, int] = defaultdict(int)

    def _client_ip(self, request: Request) -> str:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if self._per_minute <= 0 or request.method in ("GET", "HEAD", "OPTIONS"):
            return await call_next(request)
        if not request.url.path.startswith(self._LIMITED_PREFIXES):
            return await call_next(request)

        now = time.time()
        ip = self._client_ip(request)
        with self._lock:
            if now - self._window_start >= 60.0:
                self._window_start = now
                self._counts.clear()
            self._counts[ip] += 1
            over = self._counts[ip] > self._per_minute
            retry_after = int(60 - (now - self._window_start)) + 1

        if over:
            logger.warning("rate limit exceeded", extra={"client_ip": ip, "path": request.url.path})
            from starlette.responses import JSONResponse

            return JSONResponse(
                status_code=429,
                content={"error": {"code": "RATE_LIMITED", "message": "Too many requests. Slow down."}},
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
