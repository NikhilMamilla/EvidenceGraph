"""
Phase 10 — Administrative API-key authorization.

EvidenceGraph has no user-account authentication system; the only existing
secret-based access control in the project is configuration-driven signing
verification (Razorpay webhook secret). Phase 10 follows the same project
convention: a server-side configured ADMIN_API_KEY gates the restricted
audit surfaces.

Authorization tiers:
    - Public read endpoints (integrity results, trace SUMMARIES) — no key
    - Full decision-trace content          → X-API-Key (admin)
    - Cryptographic verification           → X-API-Key (admin)
    - Replay execution                     → X-API-Key (admin)

Fail-closed behaviour:
    If ADMIN_API_KEY is not configured, restricted endpoints return 503
    rather than silently permitting anonymous administrative access.

This is deliberately NOT a parallel user-authentication mechanism — it is the
project's established settings-based credential pattern applied to new
restricted surfaces.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import Header, HTTPException, status

from app.core.config import get_settings

logger = logging.getLogger(__name__)

API_KEY_HEADER = "X-API-Key"


def require_admin_api_key(
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
) -> None:
    """
    FastAPI dependency enforcing administrative authorization.

    - 401 when the API key header is missing.
    - 403 when the supplied key is wrong (constant-time comparison).
    - 503 when the server has no ADMIN_API_KEY configured (fail closed).
    """
    settings = get_settings()
    expected = settings.admin_api_key

    if not expected:
        logger.warning(
            "Restricted audit endpoint rejected: ADMIN_API_KEY not configured"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Administrative authorization is not configured on this "
                "deployment. Set ADMIN_API_KEY to enable audit-trace access."
            ),
        )

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide the 'X-API-Key' header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not hmac.compare_digest(x_api_key.encode("utf-8"), expected.encode("utf-8")):
        logger.warning("Restricted audit endpoint rejected: invalid API key")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key for audit-trace access.",
        )
