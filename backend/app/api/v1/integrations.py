"""
GET /api/v1/integrations/razorpay/status

Admin/debug endpoint — reports Razorpay ingestion health.
Never exposes secrets or full payment payloads.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.schemas.webhook import RazorpayStatusResponse
from app.services.metrics import get_metrics

logger = logging.getLogger(__name__)

router = APIRouter(tags=["integrations"])


@router.get(
    "/razorpay/status",
    response_model=RazorpayStatusResponse,
    summary="Razorpay integration status",
    description="Reports Razorpay configuration and ingestion metrics. No secrets exposed.",
)
async def razorpay_status() -> RazorpayStatusResponse:
    settings = get_settings()
    metrics = get_metrics()

    configured = bool(
        settings.razorpay_key_id
        and settings.razorpay_key_secret
        and settings.razorpay_webhook_secret
    )

    # Only expose first 8 chars of key ID — enough to identify, not to misuse
    key_id_prefix = (settings.razorpay_key_id[:8] + "...") if settings.razorpay_key_id else ""

    return RazorpayStatusResponse(
        configured=configured,
        mode=settings.razorpay_mode,
        key_id_prefix=key_id_prefix,
        last_verified_event_at=metrics.last_verified_event_at,
        events_received=metrics.webhooks_received_total,
        events_processed=metrics.webhooks_processed_total,
        events_rejected=metrics.webhooks_rejected_total,
        events_duplicate=metrics.webhooks_duplicate_total,
    )
