"""
Phase 22 — AI Schemas for Claim Extraction & Evidence Matching.

Strict Pydantic schemas for AI structured output validation.
Malformed AI output is rejected, never silently accepted.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractedClaim(BaseModel):
    """A single claim extracted from merchant defense text."""

    claim_type: str = Field(
        ...,
        description="Claim type from the delivery dispute ontology",
    )
    claim_text: str = Field(
        ...,
        description="Original text of the claim",
    )
    normalized_value: str | bool | None = Field(
        default=None,
        description="Normalized value if deterministically safe (e.g., date, boolean)",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="AI confidence in this extraction (0.0-1.0)",
    )
    source_span: str | None = Field(
        default=None,
        description="Original text span that produced this claim",
    )


class ClaimExtractionResult(BaseModel):
    """Structured output from AI claim extraction."""

    claims: list[ExtractedClaim] = Field(
        default_factory=list,
        description="Claims extracted from the defense text",
    )
    semantic_status: str = Field(
        default="OK",
        description="OK | UNPARSEABLE | AI_UNAVAILABLE",
    )
    raw_input_hash: str | None = Field(
        default=None,
        description="SHA-256 hash of the input text for audit",
    )


class EvidenceMatch(BaseModel):
    """A single evidence-claim relationship from AI matching."""

    claim_id: str = Field(
        ...,
        description="Reference to the claim this evidence relates to",
    )
    evidence_id: int = Field(
        ...,
        description="Database ID of the evidence observation",
    )
    relationship: str = Field(
        ...,
        description="RELEVANT | NOT_RELEVANT | UNCERTAIN",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="AI confidence in this relationship",
    )
    reason: str = Field(
        default="",
        description="Brief explanation of semantic relevance",
    )


class EvidenceMatchingResult(BaseModel):
    """Structured output from AI evidence matching."""

    matches: list[EvidenceMatch] = Field(
        default_factory=list,
        description="Evidence-claim relationships identified by AI",
    )
    semantic_status: str = Field(
        default="OK",
        description="OK | AI_UNAVAILABLE",
    )


class DefenseVerificationResult(BaseModel):
    """Complete end-to-end verification result."""

    case_id: str
    defense_text: str
    claims_extracted: list[ExtractedClaim]
    evidence_matches: list[EvidenceMatch]
    deterministic_result: dict
    final_decision: str
    decision_rationale: str
    ai_semantic_status: str
    deterministic_status: str
    methodology_version: str
    prompt_version: str
    ai_run_id: str | None = None


# Valid claim types for delivery disputes
VALID_CLAIM_TYPES = {
    "DELIVERY_COMPLETED",
    "CUSTOMER_RECEIVED_GOODS",
    "DELIVERY_DATE",
    "DELIVERY_LOCATION",
    "CUSTOMER_ACKNOWLEDGED_RECEIPT",
    "SHIPMENT_DISPATCHED",
    "TRACKING_EVENT_EXISTS",
}

# Valid evidence relationships (AI layer only — NOT verification)
VALID_RELATIONSHIPS = {"RELEVANT", "NOT_RELEVANT", "UNCERTAIN"}

# Valid semantic statuses
VALID_SEMANTIC_STATUSES = {"OK", "UNPARSEABLE", "AI_UNAVAILABLE"}
