"""
Phase 21 — Golden Test Case Generator & Dataset Service.

Creates 20+ deterministic golden test cases for the defense verification
evaluation. Each case is built from real EvidenceGraph structures with
documented deterministic transformations.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.defense_types import (
    EG_DEFENSE_V1_0,
    DEFENSE_VERIFICATION_METHODOLOGY_V1,
    CaseSource,
    CaseStatus,
    DisputeCategory,
    SplitType,
    VerificationLabel,
)
from app.models.defense_case import DefenseCase
from app.models.defense_claim import DefenseClaim
from app.models.defense_evidence_link import DefenseEvidenceLink
from app.models.evaluation_label import EvaluationLabel
from app.models.evaluation_dataset import EvaluationDataset
from app.models.evidence import EvidenceObservation


class GoldenTestCase:
    """In-memory representation of a golden test case before DB insertion."""

    def __init__(
        self,
        case_id: str,
        dispute_reason: str,
        description: str,
        expected_label: str,
        source: str,
        split: str,
        claims: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        rationale: str,
        payment_ref: str | None = None,
        order_ref: str | None = None,
    ):
        self.case_id = case_id
        self.dispute_reason = dispute_reason
        self.description = description
        self.expected_label = expected_label
        self.source = source
        self.split = split
        self.claims = claims
        self.evidence = evidence
        self.rationale = rationale
        self.payment_ref = payment_ref
        self.order_ref = order_ref


def get_golden_cases() -> list[GoldenTestCase]:
    """Return the 20 canonical golden test cases for Phase 21."""
    now = datetime.now(timezone.utc)

    return [
        # --- SUPPORTED cases ---
        GoldenTestCase(
            case_id="GOLDEN_001",
            dispute_reason="Customer claims merchandise not received",
            description="Fully supported delivery claim with complete evidence chain.",
            expected_label=VerificationLabel.SUPPORTED,
            source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TRAIN,
            rationale=(
                "Payment + order match. Delivery proof present from carrier API. "
                "Payment ID matches. Order ID matches. Independent sources confirm delivery."
            ),
            payment_ref="pay_golden_001",
            order_ref="order_golden_001",
            claims=[
                {
                    "claim_id": "CL_001_A",
                    "claim_text": "The package was delivered to the customer address.",
                    "claim_type": "DELIVERY_COMPLETED",
                },
            ],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_001", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_001", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_002",
            dispute_reason="Customer claims merchandise not received",
            description="Multiple independent sources confirm delivery.",
            expected_label=VerificationLabel.SUPPORTED,
            source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TRAIN,
            rationale="Two independent carriers confirm delivery. Payment and order IDs match.",
            payment_ref="pay_golden_002",
            order_ref="order_golden_002",
            claims=[
                {
                    "claim_id": "CL_002_A",
                    "claim_text": "Package was delivered and signed by recipient.",
                    "claim_type": "CUSTOMER_RECEIVED_GOODS",
                },
            ],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered_signed", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_002", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_002", "link_type": "SUPPORTING"},
                {"evidence_type": "DELIVERY_PROOF", "source_type": "MERCHANT_DOCUMENT", "value": "delivered_photo", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_003",
            dispute_reason="Customer claims merchandise not received",
            description="Delivery with customer acknowledgment.",
            expected_label=VerificationLabel.SUPPORTED,
            source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.VALIDATION,
            rationale="Delivery proof + customer email acknowledging receipt. Full coverage.",
            payment_ref="pay_golden_003",
            order_ref="order_golden_003",
            claims=[
                {
                    "claim_id": "CL_003_A",
                    "claim_text": "Package was delivered on August 15.",
                    "claim_type": "DELIVERY_DATE",
                },
                {
                    "claim_id": "CL_003_B",
                    "claim_text": "Customer acknowledged receipt via email.",
                    "claim_type": "CUSTOMER_ACKNOWLEDGED",
                },
            ],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered_2026-08-15", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_003", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_003", "link_type": "SUPPORTING"},
                {"evidence_type": "CUSTOMER_ACKNOWLEDGMENT", "source_type": "CUSTOMER_COMMUNICATION", "value": "thank_you_received", "link_type": "SUPPORTING"},
            ],
        ),

        # --- INSUFFICIENT_EVIDENCE cases ---
        GoldenTestCase(
            case_id="GOLDEN_004",
            dispute_reason="Customer claims merchandise not received",
            description="No delivery evidence at all.",
            expected_label=VerificationLabel.INSUFFICIENT_EVIDENCE,
            source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TRAIN,
            rationale="Payment exists but no delivery proof, no carrier data, no acknowledgment.",
            payment_ref="pay_golden_004",
            order_ref="order_golden_004",
            claims=[
                {
                    "claim_id": "CL_004_A",
                    "claim_text": "The package was delivered to the customer.",
                    "claim_type": "DELIVERY_COMPLETED",
                },
            ],
            evidence=[
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_004", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_004", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_005",
            dispute_reason="Customer claims merchandise not received",
            description="Payment/order evidence only, missing DELIVERY_PROOF required type.",
            expected_label=VerificationLabel.INSUFFICIENT_EVIDENCE,
            source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TRAIN,
            rationale="Coverage gap: DELIVERY_PROOF required but absent.",
            payment_ref="pay_golden_005",
            order_ref="order_golden_005",
            claims=[
                {
                    "claim_id": "CL_005_A",
                    "claim_text": "Package delivered at verified address.",
                    "claim_type": "DELIVERY_LOCATION",
                },
            ],
            evidence=[
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_005", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_006",
            dispute_reason="Customer claims merchandise not received",
            description="Partial evidence — has carrier data but no payment/order match.",
            expected_label=VerificationLabel.INSUFFICIENT_EVIDENCE,
            source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.VALIDATION,
            rationale="Coverage gap: PAYMENT_ID_MATCH and ORDER_ID_MATCH required but absent.",
            payment_ref="pay_golden_006",
            order_ref="order_golden_006",
            claims=[
                {
                    "claim_id": "CL_006_A",
                    "claim_text": "Package was delivered.",
                    "claim_type": "DELIVERY_COMPLETED",
                },
            ],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered", "link_type": "SUPPORTING"},
            ],
        ),

        # --- CONTRADICTED cases ---
        GoldenTestCase(
            case_id="GOLDEN_007",
            dispute_reason="Customer claims merchandise not received",
            description="Delivery proof exists but carrier says delivery failed.",
            expected_label=VerificationLabel.CONTRADICTED,
            source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TRAIN,
            rationale="Authoritative carrier API contradicts delivery claim.",
            payment_ref="pay_golden_007",
            order_ref="order_golden_007",
            claims=[
                {
                    "claim_id": "CL_007_A",
                    "claim_text": "The package was delivered successfully.",
                    "claim_type": "DELIVERY_COMPLETED",
                },
            ],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivery_failed", "link_type": "CONTRADICTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_007", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_007", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_008",
            dispute_reason="Customer claims merchandise not received",
            description="Refund was already issued, contradicting defense claim.",
            expected_label=VerificationLabel.CONTRADICTED,
            source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TRAIN,
            rationale="Refund event contradicts the claim that goods were delivered.",
            payment_ref="pay_golden_008",
            order_ref="order_golden_008",
            claims=[
                {
                    "claim_id": "CL_008_A",
                    "claim_text": "Customer received the goods.",
                    "claim_type": "CUSTOMER_RECEIVED_GOODS",
                },
            ],
            evidence=[
                {"evidence_type": "REFUND_STATUS", "source_type": "RAZORPAY_WEBHOOK", "value": "refunded", "link_type": "CONTRADICTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_008", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_009",
            dispute_reason="Customer claims merchandise not received",
            description="Amount mismatch between delivery and payment.",
            expected_label=VerificationLabel.CONTRADICTED,
            source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.VALIDATION,
            rationale="Delivery proof references different amount than payment.",
            payment_ref="pay_golden_009",
            order_ref="order_golden_009",
            claims=[
                {
                    "claim_id": "CL_009_A",
                    "claim_text": "Package was delivered with correct contents.",
                    "claim_type": "DELIVERY_COMPLETED",
                },
            ],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered_wrong_amount", "link_type": "CONTRADICTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_009", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_009", "link_type": "SUPPORTING"},
            ],
        ),

        # --- UNKNOWN cases ---
        GoldenTestCase(
            case_id="GOLDEN_010",
            dispute_reason="Customer claims merchandise not received",
            description="Evidence exists but provenance is unverifiable.",
            expected_label=VerificationLabel.UNKNOWN,
            source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TRAIN,
            rationale="Evidence present but source_reference is empty — provenance check fails.",
            payment_ref="pay_golden_010",
            order_ref="order_golden_010",
            claims=[
                {
                    "claim_id": "CL_010_A",
                    "claim_text": "Package was delivered.",
                    "claim_type": "DELIVERY_COMPLETED",
                },
            ],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered", "link_type": "SUPPORTING", "source_ref": ""},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_010", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_010", "link_type": "SUPPORTING"},
            ],
        ),

        # --- Edge cases ---
        GoldenTestCase(
            case_id="GOLDEN_011",
            dispute_reason="Customer claims merchandise not received",
            description="Future delivery evidence — should be excluded.",
            expected_label=VerificationLabel.INSUFFICIENT_EVIDENCE,
            source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST,
            rationale="Delivery proof dated AFTER evaluation time — temporally excluded.",
            payment_ref="pay_golden_011",
            order_ref="order_golden_011",
            claims=[
                {
                    "claim_id": "CL_011_A",
                    "claim_text": "Package was delivered.",
                    "claim_type": "DELIVERY_COMPLETED",
                },
            ],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered", "link_type": "SUPPORTING", "future": True},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_011", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_011", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_012",
            dispute_reason="Customer claims merchandise not received",
            description="Duplicate evidence from same source should not inflate support.",
            expected_label=VerificationLabel.INSUFFICIENT_EVIDENCE,
            source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST,
            rationale=(
                "Three copies of same delivery proof from same carrier. "
                "Deduplicated to 1 source. Still missing PAYMENT_ID_MATCH."
            ),
            payment_ref="pay_golden_012",
            order_ref="order_golden_012",
            claims=[
                {
                    "claim_id": "CL_012_A",
                    "claim_text": "Package was delivered.",
                    "claim_type": "DELIVERY_COMPLETED",
                },
            ],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered", "link_type": "SUPPORTING"},
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered", "link_type": "SUPPORTING"},
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_013",
            dispute_reason="Customer claims merchandise not received",
            description="Same-source corroboration does not count as independent.",
            expected_label=VerificationLabel.INSUFFICIENT_EVIDENCE,
            source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST,
            rationale=(
                "Two documents from same merchant_source both say delivered. "
                "Same source = not independent corroboration."
            ),
            payment_ref="pay_golden_013",
            order_ref="order_golden_013",
            claims=[
                {
                    "claim_id": "CL_013_A",
                    "claim_text": "Package was delivered.",
                    "claim_type": "DELIVERY_COMPLETED",
                },
            ],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "MERCHANT_DOCUMENT", "value": "delivery_note_1", "link_type": "SUPPORTING"},
                {"evidence_type": "DELIVERY_PROOF", "source_type": "MERCHANT_DOCUMENT", "value": "delivery_note_2", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_014",
            dispute_reason="Customer claims merchandise not received",
            description="Evidence linked to wrong payment — should be excluded.",
            expected_label=VerificationLabel.INSUFFICIENT_EVIDENCE,
            source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST,
            rationale="Delivery proof references different payment ID — no match.",
            payment_ref="pay_golden_014",
            order_ref="order_golden_014",
            claims=[
                {
                    "claim_id": "CL_014_A",
                    "claim_text": "Package was delivered.",
                    "claim_type": "DELIVERY_COMPLETED",
                },
            ],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_WRONG_014", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_014", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_015",
            dispute_reason="Customer claims merchandise not received",
            description="No evidence at all — completely empty case.",
            expected_label=VerificationLabel.UNKNOWN,
            source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST,
            rationale="No evidence linked to any claim. Cannot determine anything.",
            payment_ref="pay_golden_015",
            order_ref="order_golden_015",
            claims=[
                {
                    "claim_id": "CL_015_A",
                    "claim_text": "Package was delivered.",
                    "claim_type": "DELIVERY_COMPLETED",
                },
            ],
            evidence=[],
        ),
        GoldenTestCase(
            case_id="GOLDEN_016",
            dispute_reason="Customer claims merchandise not received",
            description="Delivery timestamp before payment — temporal anomaly.",
            expected_label=VerificationLabel.CONTRADICTED,
            source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST,
            rationale="Delivery proof dated before payment was made — chronologically impossible.",
            payment_ref="pay_golden_016",
            order_ref="order_golden_016",
            claims=[
                {
                    "claim_id": "CL_016_A",
                    "claim_text": "Package was delivered on the correct date.",
                    "claim_type": "DELIVERY_DATE",
                },
            ],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered_before_payment", "link_type": "CONTRADICTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_016", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_016", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_017",
            dispute_reason="Customer claims merchandise not received",
            description="Authoritative contradiction from carrier API.",
            expected_label=VerificationLabel.CONTRADICTED,
            source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TEST,
            rationale="Carrier explicitly reports 'delivery_failed' with tracking number.",
            payment_ref="pay_golden_017",
            order_ref="order_golden_017",
            claims=[
                {
                    "claim_id": "CL_017_A",
                    "claim_text": "The package was successfully delivered.",
                    "claim_type": "DELIVERY_COMPLETED",
                },
            ],
            evidence=[
                {"evidence_type": "DELIVERY_STATUS", "source_type": "CARRIER_API", "value": "delivery_failed", "link_type": "CONTRADICTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_017", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_017", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_018",
            dispute_reason="Customer claims merchandise not received",
            description="Ambiguous evidence — partial carrier data with no clear status.",
            expected_label=VerificationLabel.UNKNOWN,
            source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST,
            rationale="Evidence present but value is ambiguous — cannot determine delivery status.",
            payment_ref="pay_golden_018",
            order_ref="order_golden_018",
            claims=[
                {
                    "claim_id": "CL_018_A",
                    "claim_text": "Package was delivered.",
                    "claim_type": "DELIVERY_COMPLETED",
                },
            ],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "in_transit", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_018", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_018", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_019",
            dispute_reason="Customer claims merchandise not received",
            description="Historical evaluation — future evidence present but excluded.",
            expected_label=VerificationLabel.SUPPORTED,
            source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST,
            rationale=(
                "Evaluate as of Aug 20. Delivery evidence from Aug 22 exists but is excluded. "
                "Payment/order evidence present. However DELIVERY_PROOF required but only "
                "future one available → INSUFFICIENT at Aug 20. At Aug 23: SUPPORTED."
            ),
            payment_ref="pay_golden_019",
            order_ref="order_golden_019",
            claims=[
                {
                    "claim_id": "CL_019_A",
                    "claim_text": "Package was delivered on August 22.",
                    "claim_type": "DELIVERY_DATE",
                },
            ],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered_2026-08-22", "link_type": "SUPPORTING", "future": False},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_019", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_019", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_020",
            dispute_reason="Customer claims merchandise not received",
            description="Delivery evidence exists but source_type is unknown.",
            expected_label=VerificationLabel.UNKNOWN,
            source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST,
            rationale="Delivery proof from UNKNOWN source type — provenance check fails.",
            payment_ref="pay_golden_020",
            order_ref="order_golden_020",
            claims=[
                {
                    "claim_id": "CL_020_A",
                    "claim_text": "Package was delivered.",
                    "claim_type": "DELIVERY_COMPLETED",
                },
            ],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "UNKNOWN_SOURCE", "value": "delivered", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_020", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_020", "link_type": "SUPPORTING"},
            ],
        ),
    ]


def compute_dataset_fingerprint(cases: list[GoldenTestCase]) -> str:
    """Compute a deterministic SHA-256 fingerprint of the dataset."""
    content = json.dumps(
        [
            {
                "case_id": c.case_id,
                "expected_label": c.expected_label,
                "source": c.source,
                "split": c.split,
                "evidence_count": len(c.evidence),
            }
            for c in sorted(cases, key=lambda x: x.case_id)
        ],
        sort_keys=True,
    )
    return hashlib.sha256(content.encode()).hexdigest()


def seed_golden_cases(db: Session) -> dict[str, Any]:
    """
    Seed all golden test cases into the database.
    Returns summary of what was created.
    """
    cases = get_golden_cases()
    fingerprint = compute_dataset_fingerprint(cases)

    created_cases = 0
    created_claims = 0
    created_evidence_links = 0
    created_labels = 0

    for gc in cases:
        # Check if case already exists
        existing = (
            db.query(DefenseCase)
            .filter(DefenseCase.case_id == gc.case_id)
            .first()
        )
        if existing:
            continue

        # Create DefenseCase
        case = DefenseCase(
            case_id=gc.case_id,
            dispute_category=DisputeCategory.DELIVERY_NOT_RECEIVED,
            dispute_reason=gc.dispute_reason,
            case_description=gc.description,
            payment_reference=gc.payment_ref,
            order_reference=gc.order_ref,
            dataset_version=EG_DEFENSE_V1_0,
            case_source=gc.source,
            status=CaseStatus.CREATED,
        )
        db.add(case)
        created_cases += 1

        # Create EvidenceObservations
        evidence_obs_ids = []
        for i, ev_data in enumerate(gc.evidence):
            now = datetime.now(timezone.utc)
            observed_at = now
            if ev_data.get("future"):
                observed_at = now + timedelta(days=7)

            obs = EvidenceObservation(
                evidence_type=ev_data["evidence_type"],
                subject_type="payment",
                subject_id=gc.payment_ref or f"pay_{gc.case_id}",
                value=ev_data["value"],
                value_type="STRING",
                source_type=ev_data["source_type"],
                source_reference=ev_data.get("source_ref", f"src_{gc.case_id}_{i}"),
                observed_at=observed_at,
                extraction_method="GOLDEN_TEST_GENERATION",
                extraction_version="21.0",
                provenance_metadata={
                    "dataset_version": EG_DEFENSE_V1_0,
                    "case_id": gc.case_id,
                    "golden_test": True,
                },
            )
            db.add(obs)
            db.flush()
            evidence_obs_ids.append(obs.internal_id)

        # Create DefenseClaims
        for claim_data in gc.claims:
            claim = DefenseClaim(
                claim_id=claim_data["claim_id"],
                case_id=gc.case_id,
                claim_text=claim_data["claim_text"],
                claim_type=claim_data["claim_type"],
            )
            db.add(claim)
            created_claims += 1

            # Create DefenseEvidenceLinks
            for j, ev_data in enumerate(gc.evidence):
                if j < len(evidence_obs_ids):
                    link = DefenseEvidenceLink(
                        claim_id=claim_data["claim_id"],
                        evidence_observation_id=evidence_obs_ids[j],
                        link_type=ev_data["link_type"],
                    )
                    db.add(link)
                    created_evidence_links += 1

        # Create ground truth labels
        for claim_data in gc.claims:
            label = EvaluationLabel(
                case_id=gc.case_id,
                claim_id=claim_data["claim_id"],
                dataset_version=EG_DEFENSE_V1_0,
                label_type="GROUND_TRUTH",
                label=gc.expected_label,
                methodology_version=DEFENSE_VERIFICATION_METHODOLOGY_V1,
                labeler_id="DETERMINISTIC_REFERENCE",
                rationale=gc.rationale,
                supporting_evidence_ids=[
                    evidence_obs_ids[j]
                    for j, ev in enumerate(gc.evidence)
                    if ev["link_type"] == "SUPPORTING"
                ],
                contradicting_evidence_ids=[
                    evidence_obs_ids[j]
                    for j, ev in enumerate(gc.evidence)
                    if ev["link_type"] == "CONTRADICTING"
                ],
            )
            db.add(label)
            created_labels += 1

    # Create / refresh the dataset manifest (idempotent — safe to re-run).
    label_counts = {}
    source_counts = {}
    split_counts = {}
    for gc in cases:
        label_counts[gc.expected_label] = label_counts.get(gc.expected_label, 0) + 1
        source_counts[gc.source] = source_counts.get(gc.source, 0) + 1
        split_counts[gc.split] = split_counts.get(gc.split, 0) + 1

    dataset = (
        db.query(EvaluationDataset)
        .filter(EvaluationDataset.dataset_version == EG_DEFENSE_V1_0)
        .first()
    )
    if dataset is None:
        dataset = EvaluationDataset(
            dataset_version=EG_DEFENSE_V1_0,
            total_cases=len(cases),
            source_counts=source_counts,
            label_counts=label_counts,
            split_counts=split_counts,
            dataset_fingerprint=fingerprint,
            is_frozen=False,
            methodology_version=DEFENSE_VERIFICATION_METHODOLOGY_V1,
            description="Phase 21 golden test cases for delivery dispute defense verification.",
        )
        db.add(dataset)
    elif not dataset.is_frozen:
        # Not frozen yet: keep the manifest in step with the case definitions.
        dataset.total_cases = len(cases)
        dataset.source_counts = source_counts
        dataset.label_counts = label_counts
        dataset.split_counts = split_counts
        dataset.dataset_fingerprint = fingerprint
        dataset.methodology_version = DEFENSE_VERIFICATION_METHODOLOGY_V1

    db.commit()

    return {
        "dataset_version": EG_DEFENSE_V1_0,
        "fingerprint": fingerprint,
        "cases_created": created_cases,
        "claims_created": created_claims,
        "evidence_links_created": created_evidence_links,
        "labels_created": created_labels,
        "label_distribution": label_counts,
        "source_distribution": source_counts,
        "split_distribution": split_counts,
    }
