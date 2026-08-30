"""
POST /api/v1/webhooks/razorpay

Receives Razorpay webhook events.
Must acknowledge within 5 seconds — heavy processing is async via worker.

Security:
  - Uses raw request body for HMAC-SHA256 signature verification
  - Rejects unverified payloads with 400
  - Never logs secrets or full payloads
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_request_id
from app.db.session import get_db
from app.schemas.webhook import WebhookIngestionResponse
from app.services.webhook_service import ingest_webhook

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post(
    "/razorpay",
    response_model=WebhookIngestionResponse,
    summary="Razorpay webhook receiver",
    description=(
        "Receives Razorpay webhook events. "
        "Verifies HMAC-SHA256 signature before processing."
    ),
)
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(..., alias="X-Razorpay-Signature"),
    db: Session = Depends(get_db),
) -> WebhookIngestionResponse:
    settings = get_settings()
    request_id = get_request_id()

    if not settings.razorpay_webhook_secret:
        logger.error("RAZORPAY_WEBHOOK_SECRET not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook processing not configured",
        )

    # Read raw body — must not be parsed before signature verification
    raw_body: bytes = await request.body()

    success, result_status, event_id = ingest_webhook(
        raw_body=raw_body,
        signature_header=x_razorpay_signature,
        webhook_secret=settings.razorpay_webhook_secret,
        db=db,
        request_id=request_id,
    )

    if not success:
        if result_status == "invalid_signature":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Webhook signature verification failed",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook processing error",
        )

    return WebhookIngestionResponse(
        status="ok" if result_status != "duplicate" else "duplicate",
        event_id=event_id,
        message="Event accepted" if result_status == "accepted" else "Duplicate event",
    )
