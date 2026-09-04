"""
Phase 22 — Defense Verification Orchestrator.

Combines AI semantic understanding with deterministic EvidenceGraph verification.
AI extracts claims and identifies relevant evidence.
EvidenceGraph performs factual verification.
AI NEVER overrides deterministic results.
"""

from __future__ import annotations

import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.defense_types import (
    DEFENSE_VERIFICATION_METHODOLOGY_V1,
    EG_DEFENSE_V1_0,
    LABEL_PRECEDENCE,
    VerificationLabel,
)
from app.models.defense_case import DefenseCase
from app.models.defense_claim import DefenseClaim
from app.models.defense_evidence_link import DefenseEvidenceLink
from app.models.evidence import EvidenceObservation
from app.models.evaluation_label import EvaluationLabel
from app.schemas.defense_ai import (
    ClaimExtractionResult,
    DefenseVerificationResult,
    EvidenceMatch,
    EvidenceMatchingResult,
    ExtractedClaim,
    VALID_CLAIM_TYPES,
    VALID_RELATIONSHIPS,
)
from app.services.ai_config import get_ai_config, get_ai_provider
from app.services.defense_reference_evaluator import DefenseReferenceEvaluator


# Prompt versions
CLAIM_EXTRACTION_PROMPT_V1 = "DEFENSE_CLAIM_EXTRACTION_PROMPT_V1"
EVIDENCE_MATCHING_PROMPT_V1 = "EVIDENCE_MATCHING_PROMPT_V1"
VERIFICATION_METHODOLOGY_V2 = "DEFENSE_VERIFICATION_METHODOLOGY_V2_AI_ENHANCED"


class DefenseVerifier:
    """
    End-to-end defense verification orchestrator.

    Pipeline:
    1. AI extracts claims from defense text
    2. Deterministic retrieval of candidate evidence
    3. AI matches claims to evidence candidates
    4. Validate AI evidence references against real evidence
    5. Create DefenseClaim + DefenseEvidenceLink records
    6. Call deterministic EvidenceGraph evaluator
    7. Return final verification (deterministic authority)
    """

    def __init__(self):
        self.config = get_ai_config()
        self.evaluator = DefenseReferenceEvaluator()
        self._init_provider()

    def _init_provider(self):
        """
        Initialize the AI provider based on configuration.

        AI_PROVIDER selects test / openai / anthropic / mistral. Real providers
        self-report AI_UNAVAILABLE when no key is set — the deterministic
        evaluator still runs and retains final authority regardless.
        """
        self.provider = get_ai_provider(self.config)

    def verify_defense(
        self,
        db: Session,
        case_id: str,
        defense_text: str,
        evaluation_time: datetime | None = None,
    ) -> DefenseVerificationResult:
        """
        Full end-to-end verification pipeline.

        1. AI extracts claims
        2. Retrieve candidate evidence
        3. AI matches evidence
        4. Validate references
        5. Build verification records
        6. Run deterministic evaluator
        7. Return result
        """
        if evaluation_time is None:
            evaluation_time = datetime.now(timezone.utc)

        ai_run_id = f"AI_{uuid.uuid4().hex[:12].upper()}"

        # --- Step 1: AI Claim Extraction ---
        extraction_result = self._extract_claims(defense_text)

        # --- Step 2: Retrieve candidate evidence ---
        case = db.query(DefenseCase).filter(DefenseCase.case_id == case_id).first()
        candidate_evidence = self._retrieve_candidates(db, case)

        # --- Step 3: AI Evidence Matching ---
        matching_result = self._match_evidence(
            extraction_result.claims, candidate_evidence
        )

        # --- Step 4: Validate AI evidence references ---
        validated_matches = self._validate_references(
            matching_result.matches, candidate_evidence
        )

        # --- Step 5: Build verification records ---
        self._build_records(db, case_id, extraction_result, validated_matches)

        # --- Step 6: Run deterministic evaluator ---
        deterministic_result = self._run_deterministic(db, case, evaluation_time)

        # --- Step 7: Assemble final result ---
        return self._assemble_result(
            case_id=case_id,
            defense_text=defense_text,
            extraction=extraction_result,
            matches=validated_matches,
            deterministic=deterministic_result,
            ai_run_id=ai_run_id,
        )

    def verify_defense_batch(
        self,
        db: Session,
        items: list[tuple[str, str]],
        evaluation_time: datetime | None = None,
        max_workers: int = 8,
    ) -> dict[str, DefenseVerificationResult]:
        """
        Batch verification for many independent (case_id, defense_text) pairs —
        used by the three-way evaluation, which otherwise runs the full 50-case
        golden set through a real LLM one case at a time (two network calls
        each, fully sequential), taking minutes.

        This is not verify_defense wrapped in a thread pool. A SQLAlchemy
        Session is not safe for concurrent use from multiple threads, so every
        database read and write here stays on the calling thread. Only the
        network-bound AI calls — which never touch `db` — run concurrently:

          Phase 1 (sequential, DB reads)   — pull each case + its candidate evidence
          Phase 2 (parallel, network only) — claim extraction + evidence matching
          Phase 3 (sequential, DB writes)  — persist AI output, run the deterministic evaluator
        """
        if evaluation_time is None:
            evaluation_time = datetime.now(timezone.utc)

        prepared: list[dict[str, Any]] = []
        for case_id, defense_text in items:
            case = db.query(DefenseCase).filter(DefenseCase.case_id == case_id).first()
            prepared.append({
                "case_id": case_id,
                "defense_text": defense_text,
                "case": case,
                "candidates": self._retrieve_candidates(db, case),
            })

        def _ai_phase(item: dict[str, Any]) -> dict[str, Any]:
            extraction = self._extract_claims(item["defense_text"])
            matches = self._match_evidence(extraction.claims, item["candidates"])
            return {**item, "extraction": extraction, "matches": matches}

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            ai_results = list(pool.map(_ai_phase, prepared))

        results: dict[str, DefenseVerificationResult] = {}
        for item in ai_results:
            case_id = item["case_id"]
            validated = self._validate_references(item["matches"].matches, item["candidates"])
            self._build_records(db, case_id, item["extraction"], validated)
            deterministic = self._run_deterministic(db, item["case"], evaluation_time)
            results[case_id] = self._assemble_result(
                case_id=case_id,
                defense_text=item["defense_text"],
                extraction=item["extraction"],
                matches=validated,
                deterministic=deterministic,
                ai_run_id=f"AI_{uuid.uuid4().hex[:12].upper()}",
            )

        return results

    def _extract_claims(self, defense_text: str) -> ClaimExtractionResult:
        """AI extracts claims from defense text."""
        try:
            result = self.provider.extract_claims(defense_text)
            # Validate all claim types
            validated_claims = []
            for claim in result.claims:
                if claim.claim_type in VALID_CLAIM_TYPES:
                    validated_claims.append(claim)
            return ClaimExtractionResult(
                claims=validated_claims,
                semantic_status=result.semantic_status,
                raw_input_hash=result.raw_input_hash,
            )
        except Exception:
            return ClaimExtractionResult(
                claims=[],
                semantic_status="AI_UNAVAILABLE",
            )

    def _retrieve_candidates(
        self, db: Session, case: DefenseCase | None
    ) -> list[dict[str, Any]]:
        """Deterministically retrieve candidate evidence for matching."""
        if not case:
            return []

        # Get all evidence observations for this payment
        payment_ref = case.payment_reference
        if not payment_ref:
            return []

        observations = (
            db.query(EvidenceObservation)
            .filter(EvidenceObservation.subject_id == payment_ref)
            .all()
        )

        return [
            {
                "internal_id": obs.internal_id,
                "evidence_type": obs.evidence_type,
                "subject_type": obs.subject_type,
                "subject_id": obs.subject_id,
                "value": obs.value,
                "source_type": obs.source_type,
                "observed_at": obs.observed_at.isoformat() if obs.observed_at else None,
            }
            for obs in observations
        ]

    def _match_evidence(
        self,
        claims: list[ExtractedClaim],
        candidates: list[dict[str, Any]],
    ) -> EvidenceMatchingResult:
        """AI matches claims to candidate evidence."""
        if not claims or not candidates:
            return EvidenceMatchingResult(matches=[], semantic_status="OK")
        try:
            return self.provider.match_evidence(claims, candidates)
        except Exception:
            return EvidenceMatchingResult(matches=[], semantic_status="AI_UNAVAILABLE")

    def _validate_references(
        self,
        matches: list[EvidenceMatch],
        candidates: list[dict[str, Any]],
    ) -> list[EvidenceMatch]:
        """
        Validate that AI-generated evidence IDs exist in the candidate set.
        Hallucinated IDs are rejected.
        """
        valid_ids = {c["internal_id"] for c in candidates}
        validated = []
        for match in matches:
            if match.evidence_id in valid_ids:
                if match.relationship in VALID_RELATIONSHIPS:
                    validated.append(match)
            # Hallucinated IDs silently dropped
        return validated

    def _build_records(
        self,
        db: Session,
        case_id: str,
        extraction: ClaimExtractionResult,
        matches: list[EvidenceMatch],
    ):
        """Build DefenseClaim and DefenseEvidenceLink records from AI output."""
        # Create claims
        for i, claim in enumerate(extraction.claims):
            claim_id = f"AI_CL_{case_id}_{i:03d}"
            existing = (
                db.query(DefenseClaim)
                .filter(DefenseClaim.claim_id == claim_id)
                .first()
            )
            if not existing:
                db.add(DefenseClaim(
                    claim_id=claim_id,
                    case_id=case_id,
                    claim_text=claim.claim_text,
                    claim_type=claim.claim_type,
                ))

        db.flush()

        # Create evidence links for RELEVANT matches only
        for match in matches:
            if match.relationship == "RELEVANT":
                claim_id = f"AI_CL_{case_id}_000"  # Link to first claim
                existing_link = (
                    db.query(DefenseEvidenceLink)
                    .filter(
                        DefenseEvidenceLink.claim_id == claim_id,
                        DefenseEvidenceLink.evidence_observation_id == match.evidence_id,
                    )
                    .first()
                )
                if not existing_link:
                    db.add(DefenseEvidenceLink(
                        claim_id=claim_id,
                        evidence_observation_id=match.evidence_id,
                        link_type="SUPPORTING",
                        relevance_score=match.confidence,
                    ))

        db.flush()

    def _run_deterministic(
        self,
        db: Session,
        case: DefenseCase | None,
        evaluation_time: datetime,
    ) -> dict[str, Any]:
        """Run the existing deterministic EvidenceGraph evaluator."""
        if not case:
            return {
                "case_label": VerificationLabel.UNKNOWN,
                "rationale": "Case not found.",
                "claim_results": [],
            }
        return self.evaluator.evaluate_case(db, case, evaluation_time)

    def _assemble_result(
        self,
        case_id: str,
        defense_text: str,
        extraction: ClaimExtractionResult,
        matches: list[EvidenceMatch],
        deterministic: dict,
        ai_run_id: str,
    ) -> DefenseVerificationResult:
        """Assemble the final verification result."""
        # Final decision comes from EvidenceGraph, NOT from AI
        final_decision = deterministic.get("case_label", VerificationLabel.UNKNOWN)

        # Build rationale
        ai_claims = [c.claim_type for c in extraction.claims]
        relevant_count = sum(1 for m in matches if m.relationship == "RELEVANT")

        rationale_parts = [
            f"AI extracted {len(extraction.claims)} claim(s): {', '.join(ai_claims)}.",
            f"AI identified {relevant_count} relevant evidence link(s).",
            f"Feeded to EvidenceGraph deterministic verifier.",
            f"Final decision: {final_decision}.",
        ]
        if extraction.semantic_status != "OK":
            rationale_parts.insert(0, f"AI status: {extraction.semantic_status}.")

        return DefenseVerificationResult(
            case_id=case_id,
            defense_text=defense_text,
            claims_extracted=extraction.claims,
            evidence_matches=matches,
            deterministic_result=deterministic,
            final_decision=final_decision,
            decision_rationale=" ".join(rationale_parts),
            ai_semantic_status=extraction.semantic_status,
            deterministic_status="OK",
            methodology_version=VERIFICATION_METHODOLOGY_V2,
            prompt_version=CLAIM_EXTRACTION_PROMPT_V1,
            ai_run_id=ai_run_id,
        )
