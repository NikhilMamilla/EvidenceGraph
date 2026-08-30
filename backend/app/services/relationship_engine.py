"""
Evidence Relationship Engine — Phase 5.

Builds a typed, versioned, provenance-bearing graph of directed edges
between EvidenceObservation nodes.

Design rules enforced here:
  1. Deterministic: same evidence set → same edges.
  2. Versioned: every edge carries rule_version = CURRENT_RELATIONSHIP_RULE_VERSION.
  3. Idempotent: uses INSERT ... ON CONFLICT DO NOTHING via DB unique constraint.
  4. Auditable: every edge carries provenance_metadata explaining WHY it was created.
  5. No scoring: edges represent structural relationships only, not trust/risk/confidence.
  6. No self-loops: DB CHECK constraint enforces this; code also skips self-pairs.
  7. SAME_SOURCE ≠ independence: INDEPENDENCE_CANDIDATE is explicitly excluded
     for observations sharing the same webhook_event_id.

Relationship rules implemented in Phase 5:
  - SAME_EVENT      : same payment_event_id
  - SAME_SOURCE     : same webhook_event_id
  - SAME_PAYMENT    : same payment subject_id
  - DERIVED_FROM    : PAYMENT_STATUS/AMOUNT/CURRENCY/METHOD derived from PAYMENT_EVENT (same event)
  - INDEPENDENCE_CANDIDATE : same payment subject_id, DIFFERENT webhook_event_id
"""

from __future__ import annotations

import itertools
import logging
import time
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.evidence import EvidenceObservation
from app.models.evidence_relationship import EvidenceRelationship
from app.models.evidence_types import EvidenceType, SubjectType
from app.models.relationship_types import (
    CURRENT_RELATIONSHIP_RULE_VERSION,
    RelationshipSource,
    RelationshipType,
)

logger = logging.getLogger(__name__)

# Evidence types that are directly derived from the PAYMENT_EVENT observation
# of the same payment event group.
_DERIVED_FROM_EVENT_TYPES: frozenset[str] = frozenset({
    EvidenceType.PAYMENT_STATUS,
    EvidenceType.PAYMENT_AMOUNT,
    EvidenceType.PAYMENT_CURRENCY,
    EvidenceType.PAYMENT_METHOD,
    EvidenceType.PAYMENT_ORDER_RELATIONSHIP,
})


def _make_relationship(
    source_id: int,
    target_id: int,
    relationship_type: str,
    reason: str,
    shared_field: str | None = None,
    shared_value: Any = None,
) -> EvidenceRelationship:
    """Construct a single EvidenceRelationship. Does NOT add to session."""
    metadata: dict[str, Any] = {
        "reason": reason,
        "method": f"deterministic_rule_v{CURRENT_RELATIONSHIP_RULE_VERSION}",
    }
    if shared_field is not None:
        metadata["shared_field"] = shared_field
        metadata["shared_value"] = shared_value

    return EvidenceRelationship(
        source_evidence_id=source_id,
        target_evidence_id=target_id,
        relationship_type=relationship_type,
        relationship_source=RelationshipSource.DETERMINISTIC_RULE,
        rule_version=CURRENT_RELATIONSHIP_RULE_VERSION,
        provenance_metadata=metadata,
        # created_at set by server_default
    )


def build_relationships_for_observations(
    observations: list[EvidenceObservation],
) -> list[EvidenceRelationship]:
    """
    Apply all deterministic rules to a list of EvidenceObservation objects.

    Returns a list of EvidenceRelationship objects ready to be persisted.
    Does NOT flush or commit.

    This function is pure with respect to the database — it does not read
    from or write to the session. All required data comes from the
    observation objects passed in.

    Rules applied:
      1. SAME_EVENT       — pair-wise for observations with same payment_event_id
      2. SAME_SOURCE      — pair-wise for observations with same webhook_event_id
      3. SAME_PAYMENT     — pair-wise for observations with same payment subject_id
      4. DERIVED_FROM     — PAYMENT_EVENT is the basis; status/amount/currency/method/relationship
                            from the same event are derived from it
      5. INDEPENDENCE_CANDIDATE — pairs with same payment subject_id but different
                                  webhook_event_id (structurally distinct source events)
    """
    relationships: list[EvidenceRelationship] = []

    if not observations:
        return relationships

    # ------------------------------------------------------------------
    # Group observations for rule application
    # ------------------------------------------------------------------

    # Group by payment_event_id (for SAME_EVENT and DERIVED_FROM)
    by_payment_event: dict[int, list[EvidenceObservation]] = {}
    for obs in observations:
        if obs.payment_event_id is not None:
            by_payment_event.setdefault(obs.payment_event_id, []).append(obs)

    # Group by webhook_event_id (for SAME_SOURCE)
    by_webhook_event: dict[int, list[EvidenceObservation]] = {}
    for obs in observations:
        if obs.webhook_event_id is not None:
            by_webhook_event.setdefault(obs.webhook_event_id, []).append(obs)

    # Group by payment subject_id (for SAME_PAYMENT and INDEPENDENCE_CANDIDATE)
    by_payment_subject: dict[str, list[EvidenceObservation]] = {}
    for obs in observations:
        if obs.subject_type == SubjectType.PAYMENT:
            by_payment_subject.setdefault(obs.subject_id, []).append(obs)

    # ------------------------------------------------------------------
    # Rule 1: SAME_EVENT — all pairs within the same payment event
    # ------------------------------------------------------------------
    for pe_id, group in by_payment_event.items():
        for a, b in itertools.combinations(group, 2):
            relationships.append(
                _make_relationship(
                    source_id=a.internal_id,
                    target_id=b.internal_id,
                    relationship_type=RelationshipType.SAME_EVENT,
                    reason=f"Both observations produced by payment_event_id={pe_id}",
                    shared_field="payment_event_id",
                    shared_value=pe_id,
                )
            )

    # ------------------------------------------------------------------
    # Rule 2: SAME_SOURCE — all pairs with same webhook_event_id
    # (only add pairs NOT already covered by SAME_EVENT to avoid
    #  duplication of intent; SAME_SOURCE is a superset concept.
    #  We DO generate SAME_SOURCE in addition to SAME_EVENT when
    #  webhook_event_id differs from payment_event_id grouping.)
    # In practice for current extraction, SAME_EVENT and SAME_SOURCE
    # will cover the same pairs. We generate BOTH types to be explicit.
    # ------------------------------------------------------------------
    for we_id, group in by_webhook_event.items():
        for a, b in itertools.combinations(group, 2):
            relationships.append(
                _make_relationship(
                    source_id=a.internal_id,
                    target_id=b.internal_id,
                    relationship_type=RelationshipType.SAME_SOURCE,
                    reason=f"Both observations originated from webhook_event_id={we_id}",
                    shared_field="webhook_event_id",
                    shared_value=we_id,
                )
            )

    # ------------------------------------------------------------------
    # Rule 3: SAME_PAYMENT — all pairs describing the same payment
    # ------------------------------------------------------------------
    for pay_id, group in by_payment_subject.items():
        for a, b in itertools.combinations(group, 2):
            relationships.append(
                _make_relationship(
                    source_id=a.internal_id,
                    target_id=b.internal_id,
                    relationship_type=RelationshipType.SAME_PAYMENT,
                    reason=f"Both observations describe payment {pay_id}",
                    shared_field="subject_id",
                    shared_value=pay_id,
                )
            )

    # ------------------------------------------------------------------
    # Rule 4: DERIVED_FROM — field observations derived from PAYMENT_EVENT
    #
    # For each payment event group, find the PAYMENT_EVENT observation
    # and create DERIVED_FROM edges to status/amount/currency/method/relationship.
    # Direction: derived_obs --DERIVED_FROM--> event_obs
    # ------------------------------------------------------------------
    for pe_id, group in by_payment_event.items():
        event_obs_list = [
            o for o in group if o.evidence_type == EvidenceType.PAYMENT_EVENT
        ]
        derived_obs_list = [
            o for o in group if o.evidence_type in _DERIVED_FROM_EVENT_TYPES
        ]

        for event_obs in event_obs_list:
            for derived_obs in derived_obs_list:
                if derived_obs.internal_id == event_obs.internal_id:
                    continue
                relationships.append(
                    _make_relationship(
                        source_id=derived_obs.internal_id,
                        target_id=event_obs.internal_id,
                        relationship_type=RelationshipType.DERIVED_FROM,
                        reason=(
                            f"{derived_obs.evidence_type} is derived from "
                            f"PAYMENT_EVENT of payment_event_id={pe_id}"
                        ),
                        shared_field="payment_event_id",
                        shared_value=pe_id,
                    )
                )

    # ------------------------------------------------------------------
    # Rule 5: INDEPENDENCE_CANDIDATE
    #
    # Two observations describe the same payment (same subject_id) but
    # originated from DIFFERENT webhook_event_ids (distinct provider events).
    #
    # Explicitly EXCLUDED: pairs that share the same webhook_event_id.
    # SAME_SOURCE evidence cannot be called independent candidates.
    # ------------------------------------------------------------------
    for pay_id, group in by_payment_subject.items():
        for a, b in itertools.combinations(group, 2):
            # Skip if either has no webhook_event_id (cannot determine source)
            if a.webhook_event_id is None or b.webhook_event_id is None:
                continue
            # Skip if same source — SAME_SOURCE ≠ independence
            if a.webhook_event_id == b.webhook_event_id:
                continue
            relationships.append(
                _make_relationship(
                    source_id=a.internal_id,
                    target_id=b.internal_id,
                    relationship_type=RelationshipType.INDEPENDENCE_CANDIDATE,
                    reason=(
                        f"Observations describe payment {pay_id} but originated "
                        f"from different webhook events "
                        f"({a.webhook_event_id} vs {b.webhook_event_id}). "
                        f"Structural candidate only — not a proof of independence."
                    ),
                    shared_field="subject_id",
                    shared_value=pay_id,
                )
            )

    return relationships


def persist_relationships(
    relationships: list[EvidenceRelationship],
    db: Session,
) -> int:
    """
    Persist relationship edges to the database, ignoring duplicates.

    Uses INSERT ... ON CONFLICT DO NOTHING to honour the UNIQUE(source, target, type)
    constraint without raising an exception. This ensures the engine is idempotent:
    running it twice on the same evidence produces the same set of edges.

    Returns the count of new rows actually inserted.
    """
    if not relationships:
        return 0

    import json
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    inserted = 0
    for rel in relationships:
        stmt = pg_insert(EvidenceRelationship).values(
            source_evidence_id=rel.source_evidence_id,
            target_evidence_id=rel.target_evidence_id,
            relationship_type=rel.relationship_type,
            relationship_source=rel.relationship_source,
            rule_version=rel.rule_version,
            provenance_metadata=rel.provenance_metadata,
        ).on_conflict_do_nothing(
            index_elements=["source_evidence_id", "target_evidence_id", "relationship_type"]
        ).returning(EvidenceRelationship.internal_id)

        result = db.execute(stmt)
        if result.fetchone() is not None:
            inserted += 1

    return inserted


def _jsonb_dumps(obj: Any) -> str | None:
    """Serialize a dict to a JSON string for the JSONB column."""
    if obj is None:
        return None
    import json
    return json.dumps(obj)


def build_and_persist_relationships(
    observations: list[EvidenceObservation],
    db: Session,
) -> int:
    """
    Full pipeline: apply all deterministic rules to the given observations
    and persist the resulting edges.

    Called by the webhook worker after evidence extraction, within the
    same DB transaction.

    Returns the count of new relationship edges inserted.
    """
    start = time.perf_counter()

    relationships = build_relationships_for_observations(observations)
    inserted = persist_relationships(relationships, db)

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "Evidence relationships built",
        extra={
            "candidate_relationships": len(relationships),
            "inserted_relationships": inserted,
            "rule_version": CURRENT_RELATIONSHIP_RULE_VERSION,
            "relationship_build_duration_ms": duration_ms,
        },
    )
    return inserted


def build_relationships_for_payment(
    payment_subject_id: str,
    db: Session,
) -> int:
    """
    Load all evidence for a given payment from the DB, build relationships,
    and persist them. Returns the count of new edges inserted.

    This is the entry point for ad-hoc re-processing of a single payment's
    evidence graph (e.g. after re-running event processing).
    """
    observations = db.execute(
        select(EvidenceObservation)
        .where(
            EvidenceObservation.subject_type == SubjectType.PAYMENT,
            EvidenceObservation.subject_id == payment_subject_id,
        )
    ).scalars().all()

    return build_and_persist_relationships(list(observations), db)
