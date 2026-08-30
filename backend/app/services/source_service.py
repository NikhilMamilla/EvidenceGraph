"""
Evidence Source Quality Service — Phase 6.

Classifies the authority and directness of evidence based on its source_type
and evidence_type. These are structural properties of the provenance chain,
not a historical reliability score.

Key distinction (from the Phase 6 spec):
  - Authority: how directly the source represents the underlying fact.
  - Reliability: how often the source has been correct historically.
  These are DIFFERENT dimensions. This service handles authority/directness only.

Design:
  - Pure function — takes source_type and evidence_type, returns metadata.
  - Deterministic — same inputs always produce the same outputs.
  - No database reads in the hot path — uses an in-memory lookup table.
  - Versioned via SOURCE_QUALITY_METHODOLOGY_VERSION.
"""

from __future__ import annotations

from typing import NamedTuple

from app.models.evidence_types import EvidenceType, SourceType
from app.models.quality_types import (
    SOURCE_QUALITY_METHODOLOGY_VERSION,
    AuthorityLevel,
    SourceDirectness,
)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

class SourceQualityResult(NamedTuple):
    """Structural classification of an evidence source."""

    evidence_id: int
    source_type: str
    evidence_type: str
    authority_level: str
    """From AuthorityLevel: PRIMARY, SECONDARY, TERTIARY."""
    directness: str
    """From SourceDirectness: DIRECT, DERIVED, INFERRED."""
    description: str
    """Human-readable justification for this classification."""
    methodology_version: str


# ---------------------------------------------------------------------------
# Classification logic
# ---------------------------------------------------------------------------

# The DERIVED evidence types — these are extracted *from* a PAYMENT_EVENT
# observation in the same event, so they are structurally derived.
_DERIVED_EVIDENCE_TYPES: frozenset[str] = frozenset({
    EvidenceType.PAYMENT_STATUS,
    EvidenceType.PAYMENT_AMOUNT,
    EvidenceType.PAYMENT_CURRENCY,
    EvidenceType.PAYMENT_METHOD,
    EvidenceType.PAYMENT_ORDER_RELATIONSHIP,
    EvidenceType.ORDER_AMOUNT,
    EvidenceType.ORDER_CURRENCY,
    EvidenceType.ORDER_STATUS,
})

# The DIRECT evidence types — the root event record itself
_DIRECT_EVIDENCE_TYPES: frozenset[str] = frozenset({
    EvidenceType.PAYMENT_EVENT,
})


def _classify_directness(source_type: str, evidence_type: str) -> tuple[str, str]:
    """
    Return (directness, description) for the given (source_type, evidence_type) pair.
    """
    if source_type == SourceType.RAZORPAY_WEBHOOK:
        if evidence_type in _DIRECT_EVIDENCE_TYPES:
            return (
                SourceDirectness.DIRECT,
                "Root payment event recorded directly from a verified Razorpay webhook payload.",
            )
        elif evidence_type in _DERIVED_EVIDENCE_TYPES:
            return (
                SourceDirectness.DERIVED,
                (
                    f"{evidence_type} is extracted from a PAYMENT_EVENT observation "
                    "within the same webhook payload. It is derived from a direct observation, "
                    "not fetched independently."
                ),
            )
        else:
            return (
                SourceDirectness.DIRECT,
                "Evidence extracted directly from a verified Razorpay webhook payload.",
            )

    elif source_type == SourceType.RAZORPAY_API:
        return (
            SourceDirectness.DIRECT,
            "Evidence fetched directly from the Razorpay REST API on-demand.",
        )

    elif source_type == SourceType.INTERNAL_SYSTEM:
        return (
            SourceDirectness.DERIVED,
            "Evidence derived by EvidenceGraph internal processing from provider data.",
        )

    else:
        return (
            SourceDirectness.INFERRED,
            f"Unknown source type '{source_type}' — classified as INFERRED by default.",
        )


def _classify_authority(source_type: str) -> str:
    """
    Return AuthorityLevel for the given source_type.
    """
    if source_type in (SourceType.RAZORPAY_WEBHOOK, SourceType.RAZORPAY_API):
        return AuthorityLevel.PRIMARY
    elif source_type == SourceType.INTERNAL_SYSTEM:
        return AuthorityLevel.SECONDARY
    else:
        return AuthorityLevel.TERTIARY


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class EvidenceSourceService:
    """
    Classifies the structural source quality of an evidence observation.

    Stateless — safe to use as a module-level singleton.
    """

    def classify_by_fields(
        self,
        evidence_id: int,
        source_type: str,
        evidence_type: str,
    ) -> SourceQualityResult:
        """
        Classify source quality for raw field values.
        Pure function — no I/O.
        """
        authority = _classify_authority(source_type)
        directness, description = _classify_directness(source_type, evidence_type)

        return SourceQualityResult(
            evidence_id=evidence_id,
            source_type=source_type,
            evidence_type=evidence_type,
            authority_level=authority,
            directness=directness,
            description=description,
            methodology_version=SOURCE_QUALITY_METHODOLOGY_VERSION,
        )

    def classify(self, observation: object) -> SourceQualityResult:
        """
        Classify source quality for an EvidenceObservation ORM object.
        """
        return self.classify_by_fields(
            evidence_id=observation.internal_id,
            source_type=observation.source_type,
            evidence_type=observation.evidence_type,
        )


# Module-level singleton
source_service = EvidenceSourceService()
