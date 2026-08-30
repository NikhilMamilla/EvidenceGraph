"""
Phase 21 — Deterministic Reference Evaluator.

This is the BASELINE evaluator. It uses existing EvidenceGraph deterministic
engines (contradiction, coverage, reliability, provenance, temporal) to
produce a verification label WITHOUT any AI.

The AI layer must prove it improves on this baseline.

Methodology:
  REF_EVAL_V1  — type-presence coverage + provenance + temporal + independence.
  REF_EVAL_V2  — adds structural value semantics: an entity-match evidence item
                 must actually name the case's payment/order, and a delivery
                 proof must carry a conclusive completed-delivery status. These
                 checks are deterministic and explainable; genuinely fuzzy
                 natural-language interpretation is still left to the AI layer.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.defense_types import (
    LABEL_PRECEDENCE,
    VerificationLabel,
)
from app.models.defense_case import DefenseCase
from app.models.defense_claim import DefenseClaim
from app.models.defense_evidence_link import DefenseEvidenceLink
from app.models.evidence import EvidenceObservation
from app.models.evaluation_label import EvaluationLabel
from app.models.evaluation_run import EvaluationRun

REF_EVAL_METHODOLOGY_VERSION = "REF_EVAL_V2"

# Required evidence types for a DELIVERY_NOT_RECEIVED defense.
_REQUIRED_EVIDENCE_TYPES = {"DELIVERY_PROOF", "PAYMENT_ID_MATCH", "ORDER_ID_MATCH"}
_ENTITY_MATCH_TYPES = {"PAYMENT_ID_MATCH", "ORDER_ID_MATCH"}
_DELIVERY_STATUS_TYPES = {"DELIVERY_PROOF", "DELIVERY_STATUS"}

# A supporting delivery proof only counts if its value is a conclusive
# completed-delivery status. Anything in-progress / failed / ambiguous does not
# establish the claim (a failed status linked as CONTRADICTING is handled
# earlier by the contradiction check).
_DELIVERY_COMPLETE_PREFIXES = ("delivered", "delivery_confirmed", "received", "signed")
_DELIVERY_INCOMPLETE_TOKENS = {
    "in_transit", "out_for_delivery", "pending", "label_created", "created",
    "processing", "dispatched", "shipped", "returned", "return_to_sender",
    "failed", "delivery_failed", "lost", "exception", "on_hold", "unknown",
}


class DefenseReferenceEvaluator:
    """
    Deterministic evaluation of defense claims against evidence.

    Uses EvidenceGraph's existing deterministic engines:
    - Evidence identity (no duplicate inflation)
    - Provenance (source validity)
    - Temporal validity (no future evidence)
    - Contradiction detection
    - Coverage analysis
    - Reliability scoring

    Produces a four-class label:
    SUPPORTED / INSUFFICIENT_EVIDENCE / CONTRADICTED / UNKNOWN
    """

    def evaluate_claim(
        self,
        db: Session,
        claim: DefenseClaim,
        case: DefenseCase,
        evaluation_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Evaluate a single claim against its linked evidence."""

        if evaluation_time is None:
            evaluation_time = datetime.now(timezone.utc)

        # Get linked evidence
        links = (
            db.query(DefenseEvidenceLink)
            .filter(DefenseEvidenceLink.claim_id == claim.claim_id)
            .all()
        )

        if not links:
            return self._make_result(
                claim=claim,
                label=VerificationLabel.UNKNOWN,
                rationale="No evidence linked to this claim.",
                supporting_ids=[],
                contradicting_ids=[],
                missing_ids=[],
            )

        # Gather evidence observations
        evidence_ids = [link.evidence_observation_id for link in links]
        evidence_observations = (
            db.query(EvidenceObservation)
            .filter(EvidenceObservation.internal_id.in_(evidence_ids))
            .all()
        )
        evidence_by_id = {e.internal_id: e for e in evidence_observations}

        # --- CHECK 1: Contradiction detection ---
        contradiction_ids = []
        for link in links:
            if link.link_type == "CONTRADICTING":
                evidence = evidence_by_id.get(link.evidence_observation_id)
                if evidence and self._is_valid_for_evaluation(evidence, evaluation_time):
                    contradiction_ids.append(link.evidence_observation_id)

        if contradiction_ids:
            return self._make_result(
                claim=claim,
                label=VerificationLabel.CONTRADICTED,
                rationale=(
                    f"Authoritative contradiction detected from "
                    f"{len(contradiction_ids)} evidence source(s)."
                ),
                supporting_ids=[],
                contradicting_ids=contradiction_ids,
                missing_ids=[],
            )

        # --- CHECK 2: Temporal validity ---
        future_evidence_ids = []
        for link in links:
            evidence = evidence_by_id.get(link.evidence_observation_id)
            if evidence and not self._is_valid_for_evaluation(evidence, evaluation_time):
                future_evidence_ids.append(link.evidence_observation_id)

        # --- CHECK 3: Source independence (no duplicate inflation) ---
        valid_supporting_links = []
        seen_sources = set()
        for link in links:
            if link.link_type == "SUPPORTING":
                evidence = evidence_by_id.get(link.evidence_observation_id)
                if evidence:
                    source_key = (evidence.source_type, evidence.source_reference)
                    if source_key not in seen_sources:
                        if self._is_valid_for_evaluation(evidence, evaluation_time):
                            valid_supporting_links.append(link)
                            seen_sources.add(source_key)

        # --- CHECK 4: Provenance validity ---
        # Evidence that fails provenance is untrusted: it can neither support a
        # claim nor satisfy a coverage requirement. Filter it out first so a
        # fabricated document cannot "cover" a required evidence type.
        invalid_provenance_ids = [
            link.evidence_observation_id
            for link in valid_supporting_links
            if (evidence := evidence_by_id.get(link.evidence_observation_id)) is not None
            and not self._has_valid_provenance(evidence)
        ]
        clean_supporting = [
            l for l in valid_supporting_links
            if l.evidence_observation_id not in invalid_provenance_ids
        ]

        # --- CHECK 5: Structural value semantics (REF_EVAL_V2) ---
        # An entity-match item must actually name this case's payment/order; a
        # delivery proof must carry a conclusive completed-delivery status.
        entity_mismatch_ids: list[int] = []
        inconclusive_delivery_ids: list[int] = []
        semantically_valid: list = []
        for link in clean_supporting:
            evidence = evidence_by_id.get(link.evidence_observation_id)
            if evidence is None:
                continue
            if evidence.evidence_type in _ENTITY_MATCH_TYPES:
                if not self._entity_value_matches(evidence, case):
                    entity_mismatch_ids.append(link.evidence_observation_id)
                    continue
            elif evidence.evidence_type in _DELIVERY_STATUS_TYPES:
                status = self._delivery_value_status(evidence.value)
                if status != "COMPLETE":
                    inconclusive_delivery_ids.append(link.evidence_observation_id)
                    continue
            semantically_valid.append(link)

        # --- CHECK 6: Evidence coverage (over provenance- and value-clean set) ---
        present_types = {
            evidence.evidence_type
            for link in semantically_valid
            if (evidence := evidence_by_id.get(link.evidence_observation_id)) is not None
        }
        missing_types = _REQUIRED_EVIDENCE_TYPES - present_types

        # --- DECISION ---
        if not semantically_valid and not missing_types:
            return self._make_result(
                claim=claim,
                label=VerificationLabel.UNKNOWN,
                rationale="No supporting evidence survives provenance and value checks.",
                supporting_ids=[],
                contradicting_ids=[],
                missing_ids=list(invalid_provenance_ids),
            )

        if missing_types:
            # A delivery proof that is present but inconclusive (e.g. "in transit")
            # is a genuine "cannot tell" rather than "evidence absent".
            only_delivery_missing = missing_types == {"DELIVERY_PROOF"}
            if only_delivery_missing and inconclusive_delivery_ids:
                return self._make_result(
                    claim=claim,
                    label=VerificationLabel.UNKNOWN,
                    rationale=(
                        "Delivery evidence is present but its status is not a "
                        "conclusive completed delivery; support cannot be determined."
                    ),
                    supporting_ids=[l.evidence_observation_id for l in semantically_valid],
                    contradicting_ids=[],
                    missing_ids=list(inconclusive_delivery_ids),
                )
            reasons = [f"Required evidence missing: {', '.join(sorted(missing_types))}."]
            if entity_mismatch_ids:
                reasons.append(
                    f"{len(entity_mismatch_ids)} entity-match item(s) name a "
                    f"different payment/order."
                )
            return self._make_result(
                claim=claim,
                label=VerificationLabel.INSUFFICIENT_EVIDENCE,
                rationale=" ".join(reasons),
                supporting_ids=[l.evidence_observation_id for l in semantically_valid],
                contradicting_ids=[],
                missing_ids=list(missing_types),
            )

        # Supporting evidence present, no contradictions, coverage met.
        return self._make_result(
            claim=claim,
            label=VerificationLabel.SUPPORTED,
            rationale=(
                f"Claim supported by {len(semantically_valid)} independent "
                f"source(s) with valid provenance, temporal validity, conclusive "
                f"delivery status, entity match, and complete coverage."
            ),
            supporting_ids=[l.evidence_observation_id for l in semantically_valid],
            contradicting_ids=[],
            missing_ids=[],
        )

    @staticmethod
    def _entity_value_matches(evidence: EvidenceObservation, case: DefenseCase) -> bool:
        """A PAYMENT_ID_MATCH / ORDER_ID_MATCH item must name this case's entity."""
        value = (evidence.value or "").strip().lower()
        if not value:
            return False
        expected = {
            "PAYMENT_ID_MATCH": (case.payment_reference or "").strip().lower(),
            "ORDER_ID_MATCH": (case.order_reference or "").strip().lower(),
        }.get(evidence.evidence_type)
        # If the case carries no reference to check against, do not block on it.
        if not expected:
            return True
        return value == expected

    @staticmethod
    def _delivery_value_status(value: str | None) -> str:
        """COMPLETE | INCOMPLETE | AMBIGUOUS for a delivery-proof value."""
        v = (value or "").strip().lower()
        if not v:
            return "AMBIGUOUS"
        if v.startswith(_DELIVERY_COMPLETE_PREFIXES):
            return "COMPLETE"
        if any(tok in v for tok in _DELIVERY_INCOMPLETE_TOKENS):
            return "INCOMPLETE"
        return "AMBIGUOUS"

    def evaluate_case(
        self,
        db: Session,
        case: DefenseCase,
        evaluation_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Evaluate all claims in a case, apply label precedence."""

        claims = (
            db.query(DefenseClaim)
            .filter(DefenseClaim.case_id == case.case_id)
            .all()
        )

        if not claims:
            return {
                "case_id": case.case_id,
                "case_label": VerificationLabel.UNKNOWN,
                "claim_results": [],
                "rationale": "No claims found for this case.",
            }

        claim_results = []
        for claim in claims:
            result = self.evaluate_claim(db, claim, case, evaluation_time)
            claim_results.append(result)

        # Apply label precedence: take highest priority label
        case_label = VerificationLabel.UNKNOWN
        best_priority = LABEL_PRECEDENCE[VerificationLabel.UNKNOWN]

        for result in claim_results:
            priority = LABEL_PRECEDENCE.get(result["label"], 99)
            if priority < best_priority:
                best_priority = priority
                case_label = result["label"]

        return {
            "case_id": case.case_id,
            "case_label": case_label,
            "claim_results": claim_results,
            "rationale": f"Case label determined by label precedence across {len(claim_results)} claim(s).",
        }

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        """Coerce a datetime to timezone-aware UTC.

        Timestamps that round-trip through a backend without timezone support
        (e.g. SQLite) come back naive. Comparing a naive and an aware datetime
        raises, so normalise both sides before any temporal check.
        """
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _is_valid_for_evaluation(
        self, evidence: EvidenceObservation, evaluation_time: datetime
    ) -> bool:
        """Check if evidence is temporally valid for this evaluation point."""
        observed_at = self._as_utc(evidence.observed_at)
        valid_until = self._as_utc(evidence.valid_until)
        at = self._as_utc(evaluation_time)
        # Evidence must have been observed BEFORE or AT the evaluation time
        if observed_at is not None and at is not None and observed_at > at:
            return False
        # If evidence has a valid_until, it must not have expired
        if valid_until is not None and at is not None and valid_until < at:
            return False
        return True

    def _has_valid_provenance(self, evidence: EvidenceObservation) -> bool:
        """Check if evidence has a valid, non-empty provenance chain."""
        if not evidence.source_type:
            return False
        if not evidence.source_reference:
            return False
        # Source type must be a known type
        valid_source_types = {
            "RAZORPAY_WEBHOOK", "RAZORPAY_API", "INTERNAL_SYSTEM",
            "MERCHANT_DOCUMENT", "CARRIER_API", "CUSTOMER_COMMUNICATION",
        }
        return evidence.source_type in valid_source_types

    def _make_result(
        self,
        claim: DefenseClaim,
        label: str,
        rationale: str,
        supporting_ids: list[int],
        contradicting_ids: list[int],
        missing_ids: list[int],
    ) -> dict[str, Any]:
        return {
            "claim_id": claim.claim_id,
            "claim_text": claim.claim_text,
            "claim_type": claim.claim_type,
            "label": label,
            "rationale": rationale,
            "supporting_evidence_ids": supporting_ids,
            "contradicting_evidence_ids": contradicting_ids,
            "missing_requirement_ids": missing_ids,
        }
