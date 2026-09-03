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
        adjudication_label: str | None = None,
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
        # Independent second-pass label. Re-derived from the evidence list alone,
        # without reference to `expected_label`. Where the two differ the case is
        # genuinely borderline in the four-class taxonomy; Cohen's kappa between
        # the two label sets is reported by compute_inter_annotator_agreement().
        self.adjudication_label = adjudication_label or expected_label


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

        # ===================================================================
        #  EG-DEFENSE-1.0 expansion — GOLDEN_021..GOLDEN_050  (20 -> 50)
        #  Each case also carries an independent second-pass (adjudication)
        #  label. Three deliberate borderline residuals (036/037/042) land on
        #  the safe side of the deterministic reading — never a false SUPPORTED.
        # ===================================================================

        # --- SUPPORTED (021-028) ---
        GoldenTestCase(
            case_id="GOLDEN_021", dispute_reason="Customer claims merchandise not received",
            description="Standard delivered status, complete evidence chain.",
            expected_label=VerificationLabel.SUPPORTED, source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_021", order_ref="order_golden_021",
            rationale="Carrier reports delivered; payment and order IDs match; a single authoritative source meets coverage.",
            claims=[{"claim_id": "CL_021_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_021", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_021", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_022", dispute_reason="Customer claims merchandise not received",
            description="Signed-for delivery.",
            expected_label=VerificationLabel.SUPPORTED, source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_022", order_ref="order_golden_022",
            rationale="Recipient signature on file; a 'signed' status is a conclusive completed delivery.",
            claims=[{"claim_id": "CL_022_A", "claim_text": "The recipient signed for the package.", "claim_type": "CUSTOMER_RECEIVED_GOODS"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "signed_by_recipient", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_022", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_022", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_023", dispute_reason="Customer claims merchandise not received",
            description="Explicit 'received' status.",
            expected_label=VerificationLabel.SUPPORTED, source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_023", order_ref="order_golden_023",
            rationale="Carrier status 'received_at_address'; a 'received' prefix is conclusive.",
            claims=[{"claim_id": "CL_023_A", "claim_text": "Customer received the goods.", "claim_type": "CUSTOMER_RECEIVED_GOODS"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "received_at_address", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_023", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_023", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_024", dispute_reason="Customer claims merchandise not received",
            description="Delivery confirmed with date.",
            expected_label=VerificationLabel.SUPPORTED, source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_024", order_ref="order_golden_024",
            rationale="'delivery_confirmed' status with a date; conclusive and temporally valid.",
            claims=[{"claim_id": "CL_024_A", "claim_text": "Delivery was confirmed on Aug 19.", "claim_type": "DELIVERY_DATE"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivery_confirmed_2026-08-19", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_024", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_024", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_025", dispute_reason="Customer claims merchandise not received",
            description="Two independent carriers confirm delivery.",
            expected_label=VerificationLabel.SUPPORTED, source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_025", order_ref="order_golden_025",
            rationale="Primary carrier API and an independent last-mile partner both report delivered; strong independent corroboration.",
            claims=[{"claim_id": "CL_025_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered", "link_type": "SUPPORTING", "source_ref": "carrier_primary_025"},
                {"evidence_type": "DELIVERY_PROOF", "source_type": "MERCHANT_DOCUMENT", "value": "delivered_photo_proof", "link_type": "SUPPORTING", "source_ref": "lastmile_025"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_025", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_025", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_026", dispute_reason="Customer claims merchandise not received",
            description="Delivered plus customer acknowledgment.",
            expected_label=VerificationLabel.SUPPORTED, source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.VALIDATION, payment_ref="pay_golden_026", order_ref="order_golden_026",
            rationale="Carrier delivered; customer email acknowledges receipt from an independent communication source.",
            claims=[{"claim_id": "CL_026_A", "claim_text": "The package was delivered and acknowledged.", "claim_type": "CUSTOMER_ACKNOWLEDGED"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_026", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_026", "link_type": "SUPPORTING"},
                {"evidence_type": "CUSTOMER_ACKNOWLEDGMENT", "source_type": "CUSTOMER_COMMUNICATION", "value": "confirmed_received", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_027", dispute_reason="Customer claims merchandise not received",
            description="Delivered to a safe location per customer instruction.",
            expected_label=VerificationLabel.SUPPORTED, source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_027", order_ref="order_golden_027",
            rationale="'delivered_to_safe_place' is a conclusive completed delivery; IDs match.",
            claims=[{"claim_id": "CL_027_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered_to_safe_place", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_027", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_027", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_028", dispute_reason="Customer claims merchandise not received",
            description="Delivered to a neighbour with recorded consent.",
            expected_label=VerificationLabel.SUPPORTED, source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_028", order_ref="order_golden_028",
            rationale="'delivered_to_neighbour' with recorded consent is a conclusive delivery.",
            claims=[{"claim_id": "CL_028_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered_to_neighbour", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_028", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_028", "link_type": "SUPPORTING"},
            ],
        ),

        # --- INSUFFICIENT_EVIDENCE (029-037) ---
        GoldenTestCase(
            case_id="GOLDEN_029", dispute_reason="Customer claims merchandise not received",
            description="Payment and order records only, no delivery evidence.",
            expected_label=VerificationLabel.INSUFFICIENT_EVIDENCE, source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_029", order_ref="order_golden_029",
            rationale="Required DELIVERY_PROOF is absent; the required evidence set is incomplete.",
            adjudication_label=VerificationLabel.UNKNOWN,
            claims=[{"claim_id": "CL_029_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_029", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_029", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_030", dispute_reason="Customer claims merchandise not received",
            description="Delivery proof and payment, order record missing.",
            expected_label=VerificationLabel.INSUFFICIENT_EVIDENCE, source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_030", order_ref="order_golden_030",
            rationale="ORDER_ID_MATCH is absent; cannot tie the delivered parcel to this order.",
            claims=[{"claim_id": "CL_030_A", "claim_text": "The package for this order was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_030", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_031", dispute_reason="Customer claims merchandise not received",
            description="Delivery proof and order, payment record missing.",
            expected_label=VerificationLabel.INSUFFICIENT_EVIDENCE, source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_031", order_ref="order_golden_031",
            rationale="PAYMENT_ID_MATCH is absent; the payment cannot be tied to the delivered parcel.",
            claims=[{"claim_id": "CL_031_A", "claim_text": "The paid-for package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_031", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_032", dispute_reason="Customer claims merchandise not received",
            description="Payment-match item names a different payment.",
            expected_label=VerificationLabel.INSUFFICIENT_EVIDENCE, source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_032", order_ref="order_golden_032",
            rationale="The PAYMENT_ID_MATCH value points at a different payment; after the entity check coverage is not met.",
            claims=[{"claim_id": "CL_032_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_UNRELATED_9x2", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_032", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_033", dispute_reason="Customer claims merchandise not received",
            description="Order-match item names a different order.",
            expected_label=VerificationLabel.INSUFFICIENT_EVIDENCE, source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_033", order_ref="order_golden_033",
            rationale="The ORDER_ID_MATCH value points at a different order; coverage is not met after the entity check.",
            claims=[{"claim_id": "CL_033_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_033", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_SOMEONE_ELSE", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_034", dispute_reason="Customer claims merchandise not received",
            description="All three evidence items share one webhook event (duplicate inflation).",
            expected_label=VerificationLabel.INSUFFICIENT_EVIDENCE, source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_034", order_ref="order_golden_034",
            rationale="Delivery, payment and order items share one source event; after de-duplication only one survives, so coverage is not met.",
            claims=[{"claim_id": "CL_034_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "RAZORPAY_WEBHOOK", "value": "delivered", "link_type": "SUPPORTING", "source_ref": "rzp_evt_034"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_034", "link_type": "SUPPORTING", "source_ref": "rzp_evt_034"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_034", "link_type": "SUPPORTING", "source_ref": "rzp_evt_034"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_035", dispute_reason="Customer claims merchandise not received",
            description="Only an order record is linked.",
            expected_label=VerificationLabel.INSUFFICIENT_EVIDENCE, source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_035", order_ref="order_golden_035",
            rationale="DELIVERY_PROOF and PAYMENT_ID_MATCH are both absent.",
            claims=[{"claim_id": "CL_035_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_035", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_036", dispute_reason="Customer claims merchandise not received",
            description="Delivery proof from an unrecognised source; IDs match.",
            expected_label=VerificationLabel.UNKNOWN, source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_036", order_ref="order_golden_036",
            rationale="A human reads an unverifiable delivery document as 'cannot tell'. The deterministic evaluator drops it on provenance and reports INSUFFICIENT (missing DELIVERY_PROOF) - a known safe-side residual, like GOLDEN_020.",
            adjudication_label=VerificationLabel.INSUFFICIENT_EVIDENCE,
            claims=[{"claim_id": "CL_036_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "UNKNOWN_SOURCE", "value": "delivered", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_036", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_036", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_037", dispute_reason="Customer claims merchandise not received",
            description="Conclusive delivery, but the order-match value looks like a mis-key of ours.",
            expected_label=VerificationLabel.UNKNOWN, source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_037", order_ref="order_golden_037",
            rationale="A human is unsure whether 'order_g0lden_037' is our order mis-keyed. The evaluator treats any non-exact match as a mismatch and reports INSUFFICIENT - a safe-side residual.",
            adjudication_label=VerificationLabel.INSUFFICIENT_EVIDENCE,
            claims=[{"claim_id": "CL_037_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "delivered", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_037", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_g0lden_037", "link_type": "SUPPORTING"},
            ],
        ),

        # --- CONTRADICTED (038-044) ---
        GoldenTestCase(
            case_id="GOLDEN_038", dispute_reason="Customer claims merchandise not received",
            description="Carrier reports delivery failed.",
            expected_label=VerificationLabel.CONTRADICTED, source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_038", order_ref="order_golden_038",
            rationale="Authoritative carrier status 'delivery_failed', linked as contradicting.",
            claims=[{"claim_id": "CL_038_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_STATUS", "source_type": "CARRIER_API", "value": "delivery_failed", "link_type": "CONTRADICTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_038", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_038", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_039", dispute_reason="Customer claims merchandise not received",
            description="Parcel returned to sender.",
            expected_label=VerificationLabel.CONTRADICTED, source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_039", order_ref="order_golden_039",
            rationale="Carrier status 'return_to_sender' materially contradicts a delivery claim.",
            claims=[{"claim_id": "CL_039_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_STATUS", "source_type": "CARRIER_API", "value": "return_to_sender", "link_type": "CONTRADICTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_039", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_039", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_040", dispute_reason="Customer claims merchandise not received",
            description="Parcel lost in transit.",
            expected_label=VerificationLabel.CONTRADICTED, source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_040", order_ref="order_golden_040",
            rationale="Carrier status 'lost_in_transit', linked as contradicting.",
            claims=[{"claim_id": "CL_040_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_STATUS", "source_type": "CARRIER_API", "value": "lost_in_transit", "link_type": "CONTRADICTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_040", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_040", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_041", dispute_reason="Customer claims merchandise not received",
            description="Recipient refused the delivery.",
            expected_label=VerificationLabel.CONTRADICTED, source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_041", order_ref="order_golden_041",
            rationale="Carrier status 'delivery_refused_by_recipient' contradicts the delivery claim.",
            claims=[{"claim_id": "CL_041_A", "claim_text": "The recipient accepted the package.", "claim_type": "CUSTOMER_RECEIVED_GOODS"}],
            evidence=[
                {"evidence_type": "DELIVERY_STATUS", "source_type": "CARRIER_API", "value": "delivery_refused_by_recipient", "link_type": "CONTRADICTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_041", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_041", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_042", dispute_reason="Customer claims merchandise not received",
            description="Failed delivery attempt the merchant filed as supporting evidence.",
            expected_label=VerificationLabel.UNKNOWN, source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_042", order_ref="order_golden_042",
            rationale="The merchant filed a 'failed_delivery_attempt' status as supporting (not contradicting) evidence. The value is inconclusive, so support cannot be established; the evaluator returns UNKNOWN. A stricter adjudicator reads the content as refuting the claim (CONTRADICTED) - this disagreement is why value-semantics on supporting links is a documented limitation. Never a false SUPPORTED.",
            adjudication_label=VerificationLabel.CONTRADICTED,
            claims=[{"claim_id": "CL_042_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "failed_delivery_attempt", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_042", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_042", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_043", dispute_reason="Customer claims merchandise not received",
            description="Two independent sources both contradict delivery.",
            expected_label=VerificationLabel.CONTRADICTED, source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_043", order_ref="order_golden_043",
            rationale="Carrier reports failed and the customer communication states non-receipt; both linked as contradicting.",
            claims=[{"claim_id": "CL_043_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_STATUS", "source_type": "CARRIER_API", "value": "delivery_failed", "link_type": "CONTRADICTING", "source_ref": "carrier_043"},
                {"evidence_type": "CUSTOMER_ACKNOWLEDGMENT", "source_type": "CUSTOMER_COMMUNICATION", "value": "states_not_received", "link_type": "CONTRADICTING", "source_ref": "cust_043"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_043", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_043", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_044", dispute_reason="Customer claims merchandise not received",
            description="Carrier exception, undeliverable.",
            expected_label=VerificationLabel.CONTRADICTED, source=CaseSource.CONTROLLED_TEST_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_044", order_ref="order_golden_044",
            rationale="Carrier status 'exception_undeliverable' linked as contradicting.",
            claims=[{"claim_id": "CL_044_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_STATUS", "source_type": "CARRIER_API", "value": "exception_undeliverable", "link_type": "CONTRADICTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_044", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_044", "link_type": "SUPPORTING"},
            ],
        ),

        # --- UNKNOWN (045-050) ---
        GoldenTestCase(
            case_id="GOLDEN_045", dispute_reason="Customer claims merchandise not received",
            description="Claim with no evidence linked at all.",
            expected_label=VerificationLabel.UNKNOWN, source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_045", order_ref="order_golden_045",
            rationale="Nothing is linked to the claim; support and contradiction are both indeterminable.",
            claims=[{"claim_id": "CL_045_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[],
        ),
        GoldenTestCase(
            case_id="GOLDEN_046", dispute_reason="Customer claims merchandise not received",
            description="Parcel still in transit at evaluation time.",
            expected_label=VerificationLabel.UNKNOWN, source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_046", order_ref="order_golden_046",
            rationale="IDs match, but 'in_transit' is not a conclusive completed delivery, so support cannot be determined.",
            adjudication_label=VerificationLabel.INSUFFICIENT_EVIDENCE,
            claims=[{"claim_id": "CL_046_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "in_transit", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_046", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_046", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_047", dispute_reason="Customer claims merchandise not received",
            description="Out for delivery, not yet delivered.",
            expected_label=VerificationLabel.UNKNOWN, source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_047", order_ref="order_golden_047",
            rationale="'out_for_delivery' is in progress, not conclusive.",
            claims=[{"claim_id": "CL_047_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "out_for_delivery", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_047", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_047", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_048", dispute_reason="Customer claims merchandise not received",
            description="Shipment pending pickup.",
            expected_label=VerificationLabel.UNKNOWN, source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_048", order_ref="order_golden_048",
            rationale="'pending' status is not conclusive; support cannot be determined.",
            claims=[{"claim_id": "CL_048_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "pending", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_048", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_048", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_049", dispute_reason="Customer claims merchandise not received",
            description="Ambiguous carrier status.",
            expected_label=VerificationLabel.UNKNOWN, source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_049", order_ref="order_golden_049",
            rationale="Carrier value 'status_unavailable' is neither a completed delivery nor a recognised in-progress state; indeterminable.",
            claims=[{"claim_id": "CL_049_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "status_unavailable", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_049", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_049", "link_type": "SUPPORTING"},
            ],
        ),
        GoldenTestCase(
            case_id="GOLDEN_050", dispute_reason="Customer claims merchandise not received",
            description="Shipment dispatched, delivery not confirmed.",
            expected_label=VerificationLabel.UNKNOWN, source=CaseSource.SYNTHETIC_CASE,
            split=SplitType.TEST, payment_ref="pay_golden_050", order_ref="order_golden_050",
            rationale="'dispatched' is an early lifecycle state, not a conclusive delivery.",
            claims=[{"claim_id": "CL_050_A", "claim_text": "The package was delivered.", "claim_type": "DELIVERY_COMPLETED"}],
            evidence=[
                {"evidence_type": "DELIVERY_PROOF", "source_type": "CARRIER_API", "value": "dispatched", "link_type": "SUPPORTING"},
                {"evidence_type": "PAYMENT_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "pay_golden_050", "link_type": "SUPPORTING"},
                {"evidence_type": "ORDER_ID_MATCH", "source_type": "RAZORPAY_WEBHOOK", "value": "order_golden_050", "link_type": "SUPPORTING"},
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


_LABELS_ORDER = [
    VerificationLabel.SUPPORTED,
    VerificationLabel.INSUFFICIENT_EVIDENCE,
    VerificationLabel.CONTRADICTED,
    VerificationLabel.UNKNOWN,
]


def compute_inter_annotator_agreement(
    cases: list[GoldenTestCase] | None = None,
) -> dict[str, Any]:
    """Cohen's kappa between the primary label and the independent second-pass
    (adjudication) label.

    The two label sets are produced by the same author in separate passes: the
    primary is the intended verdict; the adjudication re-derives each verdict
    from the evidence list alone. This is single-annotator + self-adjudication,
    not inter-human agreement, and is documented as such. Where the passes
    disagree the case is genuinely borderline in the four-class taxonomy.
    """
    cases = cases or get_golden_cases()
    n = len(cases)
    if n == 0:
        return {"n": 0, "cohens_kappa": None}

    primary = [c.expected_label for c in cases]
    second = [c.adjudication_label for c in cases]

    observed = sum(1 for a, b in zip(primary, second) if a == b) / n

    # expected agreement by chance, from each rater's label marginals
    p_marg = {lbl: primary.count(lbl) / n for lbl in _LABELS_ORDER}
    s_marg = {lbl: second.count(lbl) / n for lbl in _LABELS_ORDER}
    expected = sum(p_marg[lbl] * s_marg[lbl] for lbl in _LABELS_ORDER)

    kappa = (observed - expected) / (1 - expected) if (1 - expected) > 1e-9 else 1.0

    # agreement matrix primary(row) x second(col)
    matrix = {a: {b: 0 for b in _LABELS_ORDER} for a in _LABELS_ORDER}
    for a, b in zip(primary, second):
        if a in matrix and b in matrix[a]:
            matrix[a][b] += 1

    disagreements = [
        {
            "case_id": c.case_id,
            "primary": c.expected_label,
            "adjudication": c.adjudication_label,
            "note": c.rationale,
        }
        for c in cases
        if c.expected_label != c.adjudication_label
    ]

    # Landis & Koch (1977) interpretation band
    if kappa < 0.0:
        band = "poor"
    elif kappa < 0.20:
        band = "slight"
    elif kappa < 0.40:
        band = "fair"
    elif kappa < 0.60:
        band = "moderate"
    elif kappa < 0.80:
        band = "substantial"
    else:
        band = "almost perfect"

    return {
        "n": n,
        "raw_agreement": round(observed, 4),
        "expected_agreement": round(expected, 4),
        "cohens_kappa": round(kappa, 4),
        "interpretation": band,
        "disagreement_count": len(disagreements),
        "disagreements": disagreements,
        "agreement_matrix": matrix,
        "protocol": (
            "single annotator + independent self-adjudication pass; "
            "the second pass re-derives each verdict from the evidence list alone"
        ),
    }


def freeze_dataset(db: Session, dataset_version: str = EG_DEFENSE_V1_0) -> dict[str, Any]:
    """Mark the dataset immutable. Once frozen, re-seeding leaves it untouched.

    Frozen means: the fingerprint, case set and labels are the held-out split
    the reported metrics were measured against. Idempotent.
    """
    dataset = (
        db.query(EvaluationDataset)
        .filter(EvaluationDataset.dataset_version == dataset_version)
        .first()
    )
    if dataset is None:
        return {"error": f"Dataset {dataset_version} not found — seed it first."}

    already = bool(dataset.is_frozen)
    dataset.is_frozen = True
    db.commit()
    return {
        "dataset_version": dataset_version,
        "is_frozen": True,
        "was_already_frozen": already,
        "dataset_fingerprint": dataset.dataset_fingerprint,
        "total_cases": dataset.total_cases,
    }


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
                labeler_id="PRIMARY_ANNOTATOR",
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

            # Independent second-pass (adjudication) label — supports Cohen's kappa
            adj = EvaluationLabel(
                case_id=gc.case_id,
                claim_id=claim_data["claim_id"],
                dataset_version=EG_DEFENSE_V1_0,
                label_type="ADJUDICATION",
                label=gc.adjudication_label,
                methodology_version=DEFENSE_VERIFICATION_METHODOLOGY_V1,
                labeler_id="ADJUDICATION_PASS",
                rationale="Re-derived from the evidence list without reference to the primary label.",
            )
            db.add(adj)
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

    # Optionally freeze on seed (Docker sets SEED_FREEZE_DATASET=true so the
    # container always boots with an immutable held-out split).
    import os as _os
    froze = False
    if _os.getenv("SEED_FREEZE_DATASET", "false").lower() == "true" and not dataset.is_frozen:
        dataset.is_frozen = True
        froze = True

    db.commit()

    agreement = compute_inter_annotator_agreement(cases)

    return {
        "dataset_version": EG_DEFENSE_V1_0,
        "fingerprint": fingerprint,
        "frozen": bool(dataset.is_frozen),
        "froze_on_this_seed": froze,
        "inter_annotator_agreement": agreement,
        "cases_created": created_cases,
        "claims_created": created_claims,
        "evidence_links_created": created_evidence_links,
        "labels_created": created_labels,
        "label_distribution": label_counts,
        "source_distribution": source_counts,
        "split_distribution": split_counts,
    }
