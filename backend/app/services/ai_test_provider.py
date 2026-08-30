"""
Phase 22 — Deterministic Test AI Provider.

A deterministic, non-LLM implementation used for automated testing.
Never used in production. Explicitly identified as TEST_AI_PROVIDER.

Provides deterministic claim extraction and evidence matching
for known golden case inputs.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from app.schemas.defense_ai import (
    ClaimExtractionResult,
    EvidenceMatch,
    EvidenceMatchingResult,
    ExtractedClaim,
    VALID_CLAIM_TYPES,
)


# ---------------------------------------------------------------------------
# Deterministic claim extraction rules
# ---------------------------------------------------------------------------

_DELIVERY_KEYWORDS = [
    (r"\breceived?\b", "CUSTOMER_RECEIVED_GOODS"),
    (r"\bdelivered?\b", "DELIVERY_COMPLETED"),
    (r"\bsigned?\b", "CUSTOMER_ACKNOWLEDGED_RECEIPT"),
    (r"\bdispatched?\b|\bsent\b|\bshipped?\b", "SHIPMENT_DISPATCHED"),
    (r"\btracking?\b", "TRACKING_EVENT_EXISTS"),
    (r"\blocation\b|\baddress\b", "DELIVERY_LOCATION"),
]

_DATE_PATTERNS = [
    (r"(\d{4})-(\d{2})-(\d{2})", lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}"),
    (r"(?:aug|august|sep|september|oct|october|nov|november|dec|december|jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july)\w*\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{4}))?", None),
    (r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(?:aug|august|sep|september|oct|october|nov|november|dec|december|jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july)\w*(?:\s*,?\s*(\d{4}))?", None),
]


class TestAIProvider:
    """
    Deterministic AI provider for testing.

    Uses keyword matching and regex patterns to extract claims.
    Uses evidence type matching for evidence relationships.

    NEVER called from production code paths.
    """

    provider_name = "TEST_AI_PROVIDER"

    def extract_claims(self, defense_text: str) -> ClaimExtractionResult:
        """Extract claims from defense text using deterministic rules."""
        text_lower = defense_text.lower()
        input_hash = hashlib.sha256(defense_text.encode()).hexdigest()
        claims = []

        # Extract claim types from keywords
        found_types = set()
        for pattern, claim_type in _DELIVERY_KEYWORDS:
            if re.search(pattern, text_lower):
                if claim_type not in found_types:
                    found_types.add(claim_type)
                    claims.append(ExtractedClaim(
                        claim_type=claim_type,
                        claim_text=self._extract_sentence(text_lower, pattern),
                        confidence=0.9,
                        source_span=self._find_span(defense_text, pattern),
                    ))

        # Extract date if present
        date_value = self._extract_date(defense_text)
        if date_value and "DELIVERY_DATE" not in found_types:
            claims.append(ExtractedClaim(
                claim_type="DELIVERY_DATE",
                claim_text=f"Delivery date: {date_value}",
                normalized_value=date_value,
                confidence=0.85,
            ))
        elif date_value:
            # Update existing DELIVERY_DATE claim
            for c in claims:
                if c.claim_type == "DELIVERY_DATE":
                    c.normalized_value = date_value

        status = "OK" if claims else "UNPARSEABLE"
        return ClaimExtractionResult(
            claims=claims,
            semantic_status=status,
            raw_input_hash=input_hash,
        )

    def match_evidence(
        self,
        claims: list[ExtractedClaim],
        candidate_evidence: list[dict[str, Any]],
    ) -> EvidenceMatchingResult:
        """Match claims to candidate evidence using deterministic rules."""
        matches = []

        for claim in claims:
            for evidence in candidate_evidence:
                ev_type = evidence.get("evidence_type", "")
                ev_value = (evidence.get("value") or "").lower()
                ev_id = evidence.get("internal_id")

                if ev_id is None:
                    continue

                relationship = self._determine_relationship(claim, ev_type, ev_value)

                matches.append(EvidenceMatch(
                    claim_id=claim.claim_type,
                    evidence_id=ev_id,
                    relationship=relationship,
                    confidence=0.85 if relationship == "RELEVANT" else 0.7,
                    reason=f"Test provider: {ev_type} vs {claim.claim_type}",
                ))

        return EvidenceMatchingResult(
            matches=matches,
            semantic_status="OK",
        )

    def _determine_relationship(
        self, claim: ExtractedClaim, ev_type: str, ev_value: str
    ) -> str:
        """Deterministically determine evidence relevance to a claim."""
        # Delivery evidence matches delivery claims
        if claim.claim_type in ("DELIVERY_COMPLETED", "CUSTOMER_RECEIVED_GOODS"):
            if ev_type in ("DELIVERY_PROOF", "DELIVERY_STATUS"):
                return "RELEVANT"
            if "delivered" in ev_value or "received" in ev_value:
                return "RELEVANT"

        # Payment/order matching
        if claim.claim_type in ("DELIVERY_COMPLETED", "CUSTOMER_RECEIVED_GOODS"):
            if ev_type in ("PAYMENT_ID_MATCH", "ORDER_ID_MATCH"):
                return "RELEVANT"

        # Date claims
        if claim.claim_type == "DELIVERY_DATE":
            if ev_type in ("DELIVERY_PROOF", "DELIVERY_STATUS"):
                return "RELEVANT"

        # Acknowledgment
        if claim.claim_type == "CUSTOMER_ACKNOWLEDGED_RECEIPT":
            if ev_type == "CUSTOMER_ACKNOWLEDGMENT":
                return "RELEVANT"

        # Default: uncertain
        return "UNCERTAIN"

    def _extract_sentence(self, text: str, pattern: str) -> str:
        """Extract the sentence containing the matched pattern."""
        match = re.search(pattern, text)
        if not match:
            return text[:100]
        start = text.rfind(".", 0, match.start()) + 1
        end = text.find(".", match.end())
        if end == -1:
            end = len(text)
        return text[start:end].strip()[:200]

    def _find_span(self, text: str, pattern: str) -> str | None:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)
        return None

    def _extract_date(self, text: str) -> str | None:
        """Extract a date from text deterministically."""
        # Try ISO format first
        iso_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        if iso_match:
            return f"{iso_match.group(1)}-{iso_match.group(2)}-{iso_match.group(3)}"

        # Try month name format
        month_names = {
            "jan": "01", "feb": "02", "mar": "03", "apr": "04",
            "may": "05", "jun": "06", "jul": "07", "aug": "08",
            "sep": "09", "oct": "10", "nov": "11", "dec": "12",
            "january": "01", "february": "02", "march": "03", "april": "04",
            "june": "06", "july": "07", "august": "08", "september": "09",
            "october": "10", "november": "11", "december": "12",
        }
        for month_name, month_num in month_names.items():
            pattern = r"(?:" + month_name + r")\w*\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{4}))?"
            match = re.search(
                pattern,
                text,
                re.IGNORECASE,
            )
            if match:
                day = match.group(1).zfill(2)
                year = match.group(2) if match.group(2) else "2026"
                return f"{year}-{month_num}-{day}"

        return None
