"""
Phase 7 — Claim Normalization & Association Service.

A Claim is an abstract proposition (e.g. PAYMENT_STATUS = captured, PAYMENT_AMOUNT = 50000).
Evidence observations are concrete, immutable observations that support one or more Claims.

This service is deterministic and idempotent.
"""
from __future__ import annotations

from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.evidence import EvidenceObservation
from app.models.evidence_structure import Claim, EvidenceClaimLink
from app.models.evidence_types import EvidenceType
from app.models.structure_types import ClaimType


class ClaimService:
    """
    Normalizes evidence observations into canonical propositions (Claims)
    and manages links between evidence observations and claims.
    """

    @staticmethod
    def map_observation_to_claim_spec(
        obs: EvidenceObservation,
    ) -> Optional[dict]:
        """
        Derives the canonical proposition specification from an EvidenceObservation.
        Returns a dict with (subject_type, subject_id, claim_type, claim_key, canonical_value)
        or None if no canonical proposition is applicable.
        """
        if not obs.value:
            return None

        etype = obs.evidence_type
        subject_type = obs.subject_type
        subject_id = obs.subject_id

        if etype == EvidenceType.PAYMENT_STATUS:
            return {
                "subject_type": subject_type,
                "subject_id": subject_id,
                "claim_type": ClaimType.PAYMENT_STATUS.value,
                "claim_key": "STATUS",
                "canonical_value": str(obs.value).lower().strip(),
            }
        elif etype == EvidenceType.PAYMENT_AMOUNT:
            return {
                "subject_type": subject_type,
                "subject_id": subject_id,
                "claim_type": ClaimType.PAYMENT_AMOUNT.value,
                "claim_key": "AMOUNT",
                "canonical_value": str(obs.value).strip(),
            }
        elif etype == EvidenceType.PAYMENT_CURRENCY:
            return {
                "subject_type": subject_type,
                "subject_id": subject_id,
                "claim_type": ClaimType.PAYMENT_CURRENCY.value,
                "claim_key": "CURRENCY",
                "canonical_value": str(obs.value).upper().strip(),
            }
        elif etype == EvidenceType.PAYMENT_METHOD:
            return {
                "subject_type": subject_type,
                "subject_id": subject_id,
                "claim_type": ClaimType.PAYMENT_METHOD.value,
                "claim_key": "METHOD",
                "canonical_value": str(obs.value).lower().strip(),
            }
        elif etype == EvidenceType.PAYMENT_ORDER_RELATIONSHIP:
            return {
                "subject_type": subject_type,
                "subject_id": subject_id,
                "claim_type": ClaimType.ORDER_ASSOCIATION.value,
                "claim_key": "ORDER_ID",
                "canonical_value": str(obs.value).strip(),
            }
        elif etype == EvidenceType.PAYMENT_EVENT:
            return {
                "subject_type": subject_type,
                "subject_id": subject_id,
                "claim_type": ClaimType.PAYMENT_EVENT_OCCURRENCE.value,
                "claim_key": "EVENT_TYPE",
                "canonical_value": str(obs.value).strip(),
            }
        elif etype == EvidenceType.ORDER_STATUS:
            return {
                "subject_type": subject_type,
                "subject_id": subject_id,
                "claim_type": ClaimType.PAYMENT_STATUS.value,
                "claim_key": "ORDER_STATUS",
                "canonical_value": str(obs.value).lower().strip(),
            }
        elif etype == EvidenceType.ORDER_AMOUNT:
            return {
                "subject_type": subject_type,
                "subject_id": subject_id,
                "claim_type": ClaimType.PAYMENT_AMOUNT.value,
                "claim_key": "ORDER_AMOUNT",
                "canonical_value": str(obs.value).strip(),
            }
        elif etype == EvidenceType.ORDER_CURRENCY:
            return {
                "subject_type": subject_type,
                "subject_id": subject_id,
                "claim_type": ClaimType.PAYMENT_CURRENCY.value,
                "claim_key": "ORDER_CURRENCY",
                "canonical_value": str(obs.value).upper().strip(),
            }

        return None

    @classmethod
    def process_observations(
        cls,
        db: Session,
        observations: List[EvidenceObservation],
    ) -> List[Claim]:
        """
        Deterministically processes observations, ensuring canonical Claims
        exist and links are created idempotently.
        """
        claims_map: dict[str, Claim] = {}

        for obs in observations:
            spec = cls.map_observation_to_claim_spec(obs)
            if not spec:
                continue

            dedup_key = f"{spec['subject_type']}:{spec['subject_id']}:{spec['claim_type']}:{spec['claim_key']}:{spec['canonical_value']}"

            if dedup_key in claims_map:
                claim = claims_map[dedup_key]
            else:
                claim = (
                    db.query(Claim)
                    .filter(
                        Claim.subject_type == spec["subject_type"],
                        Claim.subject_id == spec["subject_id"],
                        Claim.claim_type == spec["claim_type"],
                        Claim.claim_key == spec["claim_key"],
                        Claim.canonical_value == spec["canonical_value"],
                    )
                    .first()
                )

                if not claim:
                    claim = Claim(
                        subject_type=spec["subject_type"],
                        subject_id=spec["subject_id"],
                        claim_type=spec["claim_type"],
                        claim_key=spec["claim_key"],
                        canonical_value=spec["canonical_value"],
                    )
                    db.add(claim)
                    db.flush()

                claims_map[dedup_key] = claim

            # Ensure EvidenceClaimLink exists
            link = (
                db.query(EvidenceClaimLink)
                .filter(
                    EvidenceClaimLink.claim_id == claim.internal_id,
                    EvidenceClaimLink.evidence_id == obs.internal_id,
                )
                .first()
            )
            if not link:
                link = EvidenceClaimLink(
                    claim_id=claim.internal_id,
                    evidence_id=obs.internal_id,
                )
                db.add(link)

        db.flush()
        return list(claims_map.values())
