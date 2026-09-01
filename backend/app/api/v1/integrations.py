"""
GET /api/v1/integrations/razorpay/status

Admin/debug endpoint — reports Razorpay ingestion health.
Never exposes secrets or full payment payloads.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.webhook_event import WebhookEvent
from app.schemas.webhook import RazorpayStatusResponse
from app.services.metrics import get_metrics

logger = logging.getLogger(__name__)

router = APIRouter(tags=["integrations"])


def _count_when(condition) -> Any:  # noqa: ANN001
    """Portable conditional count (avoids the FILTER clause, which SQLite lacks)."""
    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


@router.get(
    "/razorpay/status",
    response_model=RazorpayStatusResponse,
    summary="Razorpay integration status",
    description=(
        "Reports Razorpay configuration and ingestion metrics. Totals are read "
        "from persisted webhook_events so they survive a restart; the *_since_restart "
        "counters come from the in-process metrics. No secrets exposed."
    ),
)
async def razorpay_status(db: Session = Depends(get_db)) -> RazorpayStatusResponse:
    settings = get_settings()
    metrics = get_metrics()

    configured = bool(
        settings.razorpay_key_id
        and settings.razorpay_key_secret
        and settings.razorpay_webhook_secret
    )

    # Only expose first 8 chars of key ID — enough to identify, not to misuse
    key_id_prefix = (settings.razorpay_key_id[:8] + "...") if settings.razorpay_key_id else ""

    # Persisted ingestion totals. The in-process counters reset to zero on every
    # restart, which made a system that had ingested events report "Waiting".
    received = processed = failed = 0
    last_event_at = None
    try:
        row = db.execute(
            select(
                func.count(WebhookEvent.id),
                _count_when(WebhookEvent.processing_status == "PROCESSED"),
                _count_when(WebhookEvent.processing_status == "FAILED"),
                func.max(WebhookEvent.received_at),
            )
        ).one()
        received, processed, failed, last_event_at = int(row[0] or 0), int(row[1] or 0), int(row[2] or 0), row[3]
    except Exception as exc:  # noqa: BLE001 — status must never 500
        logger.warning("razorpay_status: persisted counts unavailable: %s", type(exc).__name__)

    return RazorpayStatusResponse(
        configured=configured,
        mode=settings.razorpay_mode,
        key_id_prefix=key_id_prefix,
        last_verified_event_at=metrics.last_verified_event_at,
        last_event_at=last_event_at,
        events_received=received,
        events_processed=processed,
        events_failed=failed,
        # Rejected/duplicate deliveries are not persisted as rows — these stay
        # in-process and are therefore scoped to the current uptime.
        events_rejected=metrics.webhooks_rejected_total,
        events_duplicate=metrics.webhooks_duplicate_total,
        events_received_since_restart=metrics.webhooks_received_total,
    )
