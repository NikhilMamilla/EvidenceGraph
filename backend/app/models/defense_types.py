"""
Phase 21 — Defense Verification Domain Type Constants.

Plain string constants for the defense verification evaluation domain.
Following the project convention of using string constants, not database enums.
"""

from __future__ import annotations


class DisputeCategory:
    """Supported dispute categories. Phase 21: DELIVERY_NOT_RECEIVED only."""
    DELIVERY_NOT_RECEIVED = "DELIVERY_NOT_RECEIVED"


class ClaimType:
    """Types of defense claims. Phase 21: delivery-related claims only."""
    DELIVERY_COMPLETED = "DELIVERY_COMPLETED"
    CUSTOMER_RECEIVED_GOODS = "CUSTOMER_RECEIVED_GOODS"
    DELIVERY_DATE = "DELIVERY_DATE"
    DELIVERY_LOCATION = "DELIVERY_LOCATION"
    CUSTOMER_ACKNOWLEDGED = "CUSTOMER_ACKNOWLEDGED"


class VerificationLabel:
    """Four-class verification output taxonomy."""
    SUPPORTED = "SUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONTRADICTED = "CONTRADICTED"
    UNKNOWN = "UNKNOWN"


class CaseSource:
    """Dataset provenance classification."""
    REAL_RAZORPAY_TEST_DATA = "REAL_RAZORPAY_TEST_DATA"
    CONTROLLED_TEST_CASE = "CONTROLLED_TEST_CASE"
    SYNTHETIC_CASE = "SYNTHETIC_CASE"
    HUMAN_LABELED_CASE = "HUMAN_LABELED_CASE"


class CaseStatus:
    """Case lifecycle status."""
    CREATED = "CREATED"
    EVALUATED = "EVALUATED"
    FROZEN = "FROZEN"


class SplitType:
    """Dataset split assignment."""
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    TEST = "TEST"


# Label precedence: lower number = higher priority
LABEL_PRECEDENCE = {
    VerificationLabel.CONTRADICTED: 1,
    VerificationLabel.SUPPORTED: 2,
    VerificationLabel.INSUFFICIENT_EVIDENCE: 3,
    VerificationLabel.UNKNOWN: 4,
}

# Methodology version for Phase 21
DEFENSE_VERIFICATION_METHODOLOGY_V1 = "DEFENSE_VERIFICATION_METHODOLOGY_V1"

# Dataset version for Phase 21 initial dataset
EG_DEFENSE_V1_0 = "EG-DEFENSE-1.0"
