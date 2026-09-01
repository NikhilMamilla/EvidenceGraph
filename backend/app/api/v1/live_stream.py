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
from collections import deque
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

# In-memory recent events buffer — bounded, so it can never grow unbounded
# regardless of how long a stream stays open.
_MAX_RECENT = 50
_recent_events: "deque[dict]" = deque(maxlen=_MAX_RECENT)

# How often to emit a keep-alive heartbeat, in poll cycles (poll = 3s → ~12s).
_HEARTBEAT_EVERY = 4


def _get_recent_events() -> list[dict]:
    """Return the recent events buffer, newest first."""
    return list(reversed(_recent_events))


def _current_max(db: Session, column) -> int:
    """Highest id currently in a table (0 if empty). Lets a new stream start
    'live' — only rows created after connect are pushed."""
    return int(db.execute(select(func.coalesce(func.max(column), 0))).scalar() or 0)


async def _event_generator() -> AsyncGenerator[str, None]:
    """Generate SSE events by polling the database for new records.

    Each row is emitted exactly once: every source has its own high-water-mark
    cursor, seeded to the current max id when the stream opens, so the feed
    shows what happens from now on rather than replaying (or, previously,
    re-emitting the same rows forever).
    """
    SessionLocal = get_session_factory()

    # Seed cursors from the current table maxima → a fresh stream is truly "live".
    _seed = SessionLocal()
    try:
        last_event_id = _current_max(_seed, WebhookEvent.id)
        last_obs_id = _current_max(_seed, EvidenceObservation.internal_id)
        last_fact_id = _current_max(_seed, EvidenceFact.internal_id)
        last_conflict_id = _current_max(_seed, EvidenceConflict.internal_id)
    except Exception:  # noqa: BLE001 — a seeding failure must not kill the stream
        last_event_id = last_obs_id = last_fact_id = last_conflict_id = 0
    finally:
        _seed.close()

    cycle = 0

    while True:
        try:
            db = SessionLocal()
            try:
                # New webhook events
                for ev in db.execute(
                    select(WebhookEvent)
                    .where(WebhookEvent.id > last_event_id)
                    .order_by(WebhookEvent.id)
                    .limit(10)
                ).scalars().all():
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
                    yield f"event: webhook_event\ndata: {json.dumps(event_data)}\n\n"

                # New evidence observations
                for obs in db.execute(
                    select(EvidenceObservation)
                    .where(EvidenceObservation.internal_id > last_obs_id)
                    .order_by(EvidenceObservation.internal_id)
                    .limit(10)
                ).scalars().all():
                    last_obs_id = obs.internal_id
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

                # New facts
                for fact in db.execute(
                    select(EvidenceFact)
                    .where(EvidenceFact.internal_id > last_fact_id)
                    .order_by(EvidenceFact.internal_id)
                    .limit(10)
                ).scalars().all():
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

                # New conflicts
                for conflict in db.execute(
                    select(EvidenceConflict)
                    .where(EvidenceConflict.internal_id > last_conflict_id)
                    .order_by(EvidenceConflict.internal_id)
                    .limit(10)
                ).scalars().all():
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

        except Exception as e:  # noqa: BLE001
            logger.warning("SSE stream error: %s", e)
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

        # Keep-alive heartbeat — every few cycles, not every poll, so it does
        # not drown the feed. Carries only liveness info.
        if cycle % _HEARTBEAT_EVERY == 0:
            heartbeat = {
                "type": "heartbeat",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "buffered": len(_recent_events),
            }
            yield f"event: heartbeat\ndata: {json.dumps(heartbeat)}\n\n"

        cycle += 1
        await asyncio.sleep(3)  # poll every 3 seconds


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
