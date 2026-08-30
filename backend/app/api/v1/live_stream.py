"""
Phase 20 — Live Payment Event Stream (SSE).

Provides a Server-Sent Events endpoint that streams real-time payment
and evidence events as they are processed by the system.

Endpoints:
  GET /api/v1/stream/events          — SSE stream of all events
  GET /api/v1/stream/recent          — Recent events (non-streaming)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, desc
from sqlalchemy.orm import Session

from app.db.session import get_db, get_session_factory
from app.models.evidence import EvidenceObservation
from app.models.evidence_conflict import EvidenceConflict
from app.models.evidence_fact import EvidenceFact
from app.models.payment import Payment
from app.models.payment_event import PaymentEvent
from app.models.webhook_event import WebhookEvent

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory recent events buffer (last 50 events)
_recent_events: list[dict] = []
_MAX_RECENT = 50


def _get_recent_events() -> list[dict]:
    """Return the recent events buffer."""
    return list(reversed(_recent_events[-_MAX_RECENT:]))


async def _event_generator() -> AsyncGenerator[str, None]:
    """Generate SSE events by polling the database for new records."""
    last_event_id = 0
    last_fact_id = 0
    last_conflict_id = 0

    SessionLocal = get_session_factory()

    while True:
        try:
            db = SessionLocal()
            try:
                # Check for new webhook events
                new_events = db.execute(
                    select(WebhookEvent)
                    .where(WebhookEvent.id > last_event_id)
                    .order_by(WebhookEvent.id)
                    .limit(10)
                ).scalars().all()

                for ev in new_events:
                    last_event_id = ev.id
                    event_data = {
                        "type": "webhook_event",
                        "event_id": ev.id,
                        "event_type": ev.event_type,
                        "payment_id": ev.payment_id,
                        "status": ev.processing_status,
                        "timestamp": ev.received_at.isoformat() if ev.received_at else None,
                        "razorpay_event_id": ev.razorpay_event_id,
                    }
                    _recent_events.append(event_data)
                    if len(_recent_events) > _MAX_RECENT:
                        _recent_events.pop(0)

                    yield f"event: webhook_event\ndata: {json.dumps(event_data)}\n\n"

                # Check for new evidence observations
                new_observations = db.execute(
                    select(EvidenceObservation)
                    .where(EvidenceObservation.internal_id > last_event_id * 100)  # rough heuristic
                    .order_by(EvidenceObservation.internal_id.desc())
                    .limit(5)
                ).scalars().all()

                for obs in new_observations:
                    obs_data = {
                        "type": "evidence_observation",
                        "evidence_id": obs.internal_id,
                        "evidence_type": obs.evidence_type,
                        "subject_id": obs.subject_id,
                        "value": obs.value,
                        "source_type": obs.source_type,
                        "timestamp": obs.observed_at.isoformat() if obs.observed_at else None,
                    }
                    _recent_events.append(obs_data)
                    yield f"event: evidence_observed\ndata: {json.dumps(obs_data)}\n\n"

                # Check for new facts
                new_facts = db.execute(
                    select(EvidenceFact)
                    .where(EvidenceFact.internal_id > last_fact_id)
                    .order_by(EvidenceFact.internal_id)
                    .limit(5)
                ).scalars().all()

                for fact in new_facts:
                    last_fact_id = fact.internal_id
                    fact_data = {
                        "type": "fact_reconciled",
                        "fact_id": fact.internal_id,
                        "fact_type": fact.fact_type,
                        "payment_id": fact.payment_id,
                        "canonical_value": fact.canonical_value,
                        "observation_count": fact.observation_count,
                        "timestamp": fact.first_observed_at.isoformat() if fact.first_observed_at else None,
                    }
                    _recent_events.append(fact_data)
                    yield f"event: fact_reconciled\ndata: {json.dumps(fact_data)}\n\n"

                # Check for new conflicts
                new_conflicts = db.execute(
                    select(EvidenceConflict)
                    .where(EvidenceConflict.internal_id > last_conflict_id)
                    .order_by(EvidenceConflict.internal_id)
                    .limit(5)
                ).scalars().all()

                for conflict in new_conflicts:
                    last_conflict_id = conflict.internal_id
                    conflict_data = {
                        "type": "conflict_detected",
                        "conflict_id": conflict.internal_id,
                        "payment_id": conflict.payment_id,
                        "conflict_type": conflict.conflict_type,
                        "severity": conflict.severity,
                        "status": conflict.status,
                        "timestamp": conflict.detected_at.isoformat() if conflict.detected_at else None,
                    }
                    _recent_events.append(conflict_data)
                    yield f"event: conflict_detected\ndata: {json.dumps(conflict_data)}\n\n"

            finally:
                db.close()

        except Exception as e:
            logger.warning("SSE stream error: %s", e)
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

        # Send heartbeat every cycle
        heartbeat = {
            "type": "heartbeat",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "recent_count": len(_recent_events),
        }
        yield f"event: heartbeat\ndata: {json.dumps(heartbeat)}\n\n"

        await asyncio.sleep(3)  # Poll every 3 seconds


@router.get(
    "/stream/events",
    summary="Live payment event stream (SSE)",
    description="Server-Sent Events stream of real-time payment and evidence events.",
)
async def stream_events():
    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/stream/recent",
    summary="Recent events (non-streaming)",
    description="Returns the most recent events from the in-memory buffer.",
)
def get_recent_events():
    return {
        "events": _get_recent_events(),
        "total": len(_recent_events),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get(
    "/stream/stats",
    summary="Live stream statistics",
)
def get_stream_stats():
    """Return statistics about the live event stream."""
    return {
        "buffer_size": len(_recent_events),
        "max_buffer": _MAX_RECENT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "active",
    }
