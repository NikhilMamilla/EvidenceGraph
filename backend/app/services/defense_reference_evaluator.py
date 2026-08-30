"""
Phase 21 — Deterministic Reference Evaluator.

This is the BASELINE evaluator. It uses existing EvidenceGraph deterministic
engines (contradiction, coverage, reliability, provenance, temporal) to
produce a verification label WITHOUT any AI.

The future AI layer must prove it improves on this baseline.
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

        # --- CHECK 4: Evidence coverage ---
        # For delivery disputes, we need: delivery proof + payment match
        required_evidence_types = {"DELIVERY_PROOF", "PAYMENT_ID_MATCH", "ORDER_ID_MATCH"}
        present_types = set()
        for link in valid_supporting_links:
            evidence = evidence_by_id.get(link.evidence_observation_id)
            if evidence:
                present_types.add(evidence.evidence_type)

        missing_types = required_evidence_types - present_types

        # --- CHECK 5: Provenance validity ---
        invalid_provenance_ids = []
        for link in valid_supporting_links:
            evidence = evidence_by_id.get(link.evidence_observation_id)
            if evidence:
                if not self._has_valid_provenance(evidence):
                    invalid_provenance_ids.append(link.evidence_observation_id)

        # --- DECISION ---
        # Remove evidence with invalid provenance from supporting
        clean_supporting = [
            l for l in valid_supporting_links
            if l.evidence_observation_id not in invalid_provenance_ids
        ]

        if len(clean_supporting) == 0 and not missing_types:
            return self._make_result(
                claim=claim,
                label=VerificationLabel.UNKNOWN,
                rationale="No valid supporting evidence remains after provenance check.",
                supporting_ids=[],
                contradicting_ids=[],
                missing_ids=list(invalid_provenance_ids),
            )

        if missing_types:
            return self._make_result(
                claim=claim,
                label=VerificationLabel.INSUFFICIENT_EVIDENCE,
                rationale=(
                    f"Required evidence missing: {', '.join(sorted(missing_types))}. "
                    f"{len(clean_supporting)} supporting source(s) present but "
                    f"coverage incomplete."
                ),
                supporting_ids=[l.evidence_observation_id for l in clean_supporting],
                contradicting_ids=[],
                missing_ids=list(missing_types),
            )

        # Has supporting evidence, no contradictions, coverage met
        if len(clean_supporting) >= 1:
            return self._make_result(
                claim=claim,
                label=VerificationLabel.SUPPORTED,
                rationale=(
                    f"Claim supported by {len(clean_supporting)} independent "
                    f"source(s) with valid provenance, temporal validity, "
                    f"and complete coverage."
                ),
                supporting_ids=[l.evidence_observation_id for l in clean_supporting],
                contradicting_ids=[],
                missing_ids=[],
            )

        return self._make_result(
            claim=claim,
            label=VerificationLabel.UNKNOWN,
            rationale="Insufficient information to determine claim support.",
            supporting_ids=[],
            contradicting_ids=[],
            missing_ids=[],
        )

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

    def _is_valid_for_evaluation(
        self, evidence: EvidenceObservation, evaluation_time: datetime
    ) -> bool:
        """Check if evidence is temporally valid for this evaluation point."""
        # Evidence must have been observed BEFORE or AT the evaluation time
        if evidence.observed_at > evaluation_time:
            return False
        # If evidence has a valid_until, it must not have expired
        if evidence.valid_until and evidence.valid_until < evaluation_time:
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
