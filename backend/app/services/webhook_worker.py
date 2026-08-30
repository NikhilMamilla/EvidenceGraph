"""
Background webhook event processor.

Reads event IDs from Redis queue, retrieves events from PostgreSQL,
normalizes them, updates payment/order references, and marks events processed.

Runs as a separate thread started during application lifespan.
Source of truth: PostgreSQL. Redis is transient notification only.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_session_factory
from app.integrations.razorpay.normalizer import extract_payment_status, normalize_event
from app.models.customer_reference import CustomerReference
from app.models.order import Order
from app.models.payment import Payment
from app.models.payment_event import PaymentEvent
from app.models.webhook_event import WebhookEvent
from app.schemas.webhook import ProcessingStatus
from app.services.evidence_service import extract_and_persist_evidence
from app.services.relationship_engine import build_and_persist_relationships
from app.services.metrics import get_metrics
from app.services.redis_client import get_redis_client
from app.services.webhook_service import REDIS_WEBHOOK_QUEUE

logger = logging.getLogger(__name__)

_worker_thread: threading.Thread | None = None
_stop_event = threading.Event()

MAX_EVENT_RETRIES = 5
RECOVERY_BATCH_LIMIT = 100


def _get_status_rank(status: str) -> int:
    ranks = {
        "unknown": 0,
        "created": 1,
        "authorized": 2,
        "captured": 3,
        "failed": 3,
        "paid": 3,
    }
    return ranks.get(status, 0)


def _process_event(event_id: int, db: Session) -> None:
    """Process a single webhook event by DB id."""
    metrics = get_metrics()

    event = db.get(WebhookEvent, event_id)
    if event is None:
        logger.warning("Worker: event not found in DB", extra={"webhook_event_id": event_id})
        return

    if event.processing_status == ProcessingStatus.PROCESSED:
        logger.info("Worker: event already processed", extra={"webhook_event_id": event_id})
        return

    start = time.perf_counter()

    try:
        received_at = event.received_at or datetime.now(tz=timezone.utc)
        normalized = normalize_event(event.raw_payload, received_at)

        if normalized is None:
            # Unsupported event type — mark processed, no further action
            event.processing_status = ProcessingStatus.PROCESSED
            db.commit()
            metrics.inc_processed()
            return

        payment_status = extract_payment_status(normalized.event_type)
        event_time = normalized.event_timestamp or received_at

        # 1. CustomerReference
        customer_ref_id = None
        if normalized.customer_id:
            customer_ref = db.execute(
                select(CustomerReference).where(
                    CustomerReference.razorpay_customer_id == normalized.customer_id
                )
            ).scalar_one_or_none()

            if customer_ref is None:
                customer_ref = CustomerReference(
                    razorpay_customer_id=normalized.customer_id,
                )
                db.add(customer_ref)
                db.flush()
            else:
                customer_ref.updated_at = datetime.now(tz=timezone.utc)
                db.flush()
            customer_ref_id = customer_ref.internal_id

        # 2. Order
        order_internal_id = None
        if normalized.order_id:
            order = db.execute(
                select(Order).where(
                    Order.razorpay_order_id == normalized.order_id
                )
            ).scalar_one_or_none()

            if order is None:
                order = Order(
                    razorpay_order_id=normalized.order_id,
                    amount_minor=normalized.amount_minor,
                    currency=normalized.currency,
                    status=payment_status if normalized.entity_type == "order" else "unknown",
                )
                db.add(order)
                db.flush()
            else:
                if normalized.entity_type == "order":
                    order.status = payment_status
                order.updated_at = datetime.now(tz=timezone.utc)
                db.flush()
            order_internal_id = order.internal_id

        # 3. Payment
        payment_internal_id = None
        if normalized.payment_id:
            payment = db.execute(
                select(Payment).where(
                    Payment.razorpay_payment_id == normalized.payment_id
                )
            ).scalar_one_or_none()

            if payment is None:
                payment = Payment(
                    razorpay_payment_id=normalized.payment_id,
                    order_id=order_internal_id,
                    customer_id=customer_ref_id,
                    amount_minor=normalized.amount_minor,
                    currency=normalized.currency,
                    status=payment_status,
                    payment_method_type=normalized.payment_method_type,
                    payment_method_details=normalized.payment_method_details,
                    captured=(payment_status == "captured"),
                    first_observed_at=event_time,
                    last_observed_at=event_time,
                )
                db.add(payment)
                db.flush()
            else:
                # Apply Semantic State-Transition Policy
                old_rank = _get_status_rank(payment.status)
                new_rank = _get_status_rank(payment_status)
                
                should_update_status = False
                if new_rank > old_rank:
                    should_update_status = True
                elif new_rank == old_rank and event_time > payment.last_observed_at:
                    should_update_status = True

                if should_update_status:
                    payment.status = payment_status
                    if payment_status == "captured":
                        payment.captured = True
                
                if event_time > payment.last_observed_at:
                    payment.last_observed_at = event_time
                if event_time < payment.first_observed_at:
                    payment.first_observed_at = event_time
                    
                # Update missing fields if we have them now
                if not payment.order_id and order_internal_id:
                    payment.order_id = order_internal_id
                if not payment.customer_id and customer_ref_id:
                    payment.customer_id = customer_ref_id
                if not payment.amount_minor and normalized.amount_minor:
                    payment.amount_minor = normalized.amount_minor
                if not payment.currency and normalized.currency:
                    payment.currency = normalized.currency
                if not payment.payment_method_type and normalized.payment_method_type:
                    payment.payment_method_type = normalized.payment_method_type
                if not payment.payment_method_details and normalized.payment_method_details:
                    payment.payment_method_details = normalized.payment_method_details

                payment.updated_at = datetime.now(tz=timezone.utc)
                db.flush()
            payment_internal_id = payment.internal_id

        # 4. PaymentEvent + Evidence extraction
        if payment_internal_id:
            payment_event = db.execute(
                select(PaymentEvent).where(
                    PaymentEvent.webhook_event_id == event_id
                )
            ).scalar_one_or_none()

            evidence_count = 0
            if payment_event is None:
                payment_event = PaymentEvent(
                    payment_id=payment_internal_id,
                    webhook_event_id=event_id,
                    event_type=normalized.event_type,
                    event_timestamp=event_time,
                )
                db.add(payment_event)
                db.flush()  # assign payment_event.internal_id before evidence extraction

                # Extract evidence observations within the same transaction.
                # If evidence extraction fails the whole event is rolled back.
                from app.services.evidence_service import extract_evidence_from_payment_event
                observations = extract_evidence_from_payment_event(payment_event, event)
                for obs in observations:
                    db.add(obs)
                db.flush()  # assign IDs before relationship building
                evidence_count = len(observations)

                # Build evidence relationships in the same transaction.
                # Idempotent: ON CONFLICT DO NOTHING.
                build_and_persist_relationships(observations, db)

                # Measure evidence quality at the time of processing.
                # Creates EvidenceQualitySnapshot records — does not mutate evidence.
                from app.services.quality_engine import measure_quality_for_observations
                measurement_time = datetime.now(tz=timezone.utc)
                measure_quality_for_observations(observations, measurement_time, db)

                # Evaluate evidence structure, claims, groups & corroboration (Phase 7)
                from app.services.structure_engine import StructureEngine
                if normalized.payment_id:
                    StructureEngine.evaluate_payment_structure(db, normalized.payment_id, measurement_time)

                # Evaluate temporal consistency & contradictions (Phase 8)
                from app.services.contradiction_engine import ContradictionEngine
                if normalized.payment_id:
                    ContradictionEngine.evaluate_payment_consistency(db, normalized.payment_id, measurement_time)

                # Compute evidence integrity snapshot (Phase 9) and record
                # its decision trace (Phase 10). The trace wraps the same
                # authoritative computation; a failure produces an auditable
                # FAILED trace instead of a silent gap in history.
                from app.services.integrity_trace_service import IntegrityTraceService
                if normalized.payment_id:
                    IntegrityTraceService.record_evaluation(
                        db,
                        normalized.payment_id,
                        measurement_time,
                        trigger="WEBHOOK_PROCESSING",
                    )

                # Phase 11 — Evidence state snapshot + temporal change detection.
                # Non-blocking: failures are logged but must NOT roll back the
                # webhook transaction or change event.processing_status.
                if normalized.payment_id:
                    try:
                        from app.services.evolution_snapshot_service import (
                            EvidenceStateSnapshotService,
                        )
                        from app.services.evolution_change_engine import (
                            EvidenceChangeEngine,
                        )
                        from app.models.evolution_models import EvidenceStateSnapshot
                        from sqlalchemy import select as _select

                        current_snap = EvidenceStateSnapshotService.take_snapshot(
                            db,
                            normalized.payment_id,
                            measurement_time,
                        )
                        # Find the most recent preceding snapshot for this payment.
                        prev_snap = db.execute(
                            _select(EvidenceStateSnapshot)
                            .where(
                                EvidenceStateSnapshot.payment_id == normalized.payment_id,
                                EvidenceStateSnapshot.internal_id != current_snap.internal_id,
                            )
                            .order_by(EvidenceStateSnapshot.evaluation_time.desc())
                            .limit(1)
                        ).scalars().first()

                        if prev_snap is not None:
                            EvidenceChangeEngine.detect_and_persist_changes(
                                db,
                                normalized.payment_id,
                                prev_snap,
                                current_snap,
                            )
                    except Exception as _p11_exc:
                        logger.warning(
                            "Phase 11 change detection failed (non-blocking): %s",
                            type(_p11_exc).__name__,
                            extra={
                                "payment_id": normalized.payment_id,
                                "error": str(_p11_exc)[:200],
                            },
                        )

        event.processing_status = ProcessingStatus.PROCESSED
        event.processed_at = datetime.now(tz=timezone.utc)
        event.processing_error = None
        db.commit()

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        metrics.inc_processed()
        logger.info(
            "Webhook event processed",
            extra={
                "webhook_event_id": event_id,
                "event_type": normalized.event_type,
                "payment_id": normalized.payment_id,
                "order_id": normalized.order_id,
                "evidence_count": evidence_count,
                "processing_duration_ms": duration_ms,
            },
        )

    except Exception as exc:
        db.rollback()
        event.processing_status = ProcessingStatus.FAILED
        event.processing_error = str(exc)
        event.retry_count = (event.retry_count or 0) + 1
        db.commit()
        metrics.inc_failed()
        logger.error(
            "Webhook event processing failed: %s",
            type(exc).__name__,
            extra={"webhook_event_id": event_id},
        )


def _recover_interrupted_events(SessionLocal) -> int:
    """
    Re-queue events that were durably persisted but never completed processing
    (worker crash, restart, or a transient failure). PostgreSQL is the source
    of truth; Redis is a transient notification channel, so recovery is done
    by replaying event IDs from the DB.

    FAILED events are retried up to MAX_EVENT_RETRIES so poison messages are
    not replayed forever.
    """
    requeued = 0
    db: Session = SessionLocal()
    try:
        redis = get_redis_client()
        candidates = db.execute(
            select(WebhookEvent)
            .where(
                WebhookEvent.processing_status.in_(
                    [
                        ProcessingStatus.RECEIVED,
                        ProcessingStatus.PERSISTED,
                        ProcessingStatus.FAILED,
                    ]
                ),
                WebhookEvent.retry_count < MAX_EVENT_RETRIES,
            )
            .order_by(WebhookEvent.id)
            .limit(RECOVERY_BATCH_LIMIT)
        ).scalars().all()

        for ev in candidates:
            redis.lpush(REDIS_WEBHOOK_QUEUE, str(ev.id))
            requeued += 1

        if requeued:
            logger.info("Worker recovery: re-queued %d interrupted event(s)", requeued)
    except Exception as exc:
        logger.warning("Worker recovery skipped: %s", type(exc).__name__)
    finally:
        db.close()
    return requeued


def _worker_loop() -> None:
    """Main worker loop — drains Redis queue continuously."""
    SessionLocal = get_session_factory()
    logger.info("Webhook worker started")
    _recover_interrupted_events(SessionLocal)

    while not _stop_event.is_set():
        try:
            redis = get_redis_client()
            # Block for up to 2s waiting for a new event
            result = redis.brpop(REDIS_WEBHOOK_QUEUE, timeout=2)
            if result is None:
                continue
            _, event_id_str = result
            try:
                event_id = int(event_id_str)
            except (ValueError, TypeError):
                logger.warning("Worker: invalid event ID from Redis: %s", event_id_str)
                continue

            db: Session = SessionLocal()
            try:
                _process_event(event_id, db)
            finally:
                db.close()

        except Exception as exc:
            if not _stop_event.is_set():
                logger.warning("Worker loop error: %s", type(exc).__name__)
            time.sleep(1)

    logger.info("Webhook worker stopped")


def start_worker() -> None:
    global _worker_thread, _stop_event
    _stop_event.clear()
    _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="webhook-worker")
    _worker_thread.start()


def stop_worker() -> None:
    global _stop_event
    _stop_event.set()
    if _worker_thread is not None:
        _worker_thread.join(timeout=5)
