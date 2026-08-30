"""
Phase 10 — Cryptographic trace verification.

verify_trace_integrity(trace_id)
    1. Retrieve the finalized trace.
    2. Reconstruct the canonical payload from the stored canonical_payload.
    3. Recompute SHA-256 over its canonical serialization.
    4. Compare (constant-time) against the stored trace_hash.
    5. Return VALID / INVALID / VERIFICATION_UNAVAILABLE.

verify_trace_chain(payment_id)
    Independently recomputes every finalized EVALUATION trace hash and checks
    that each trace's previous_trace_hash/previous_trace_id equals its
    predecessor's stored values. Returns CHAIN_VALID / CHAIN_INVALID /
    CHAIN_START semantics.

Honest scope: these checks make TAMPERING EVIDENT. They do not prove the
database cannot be modified, and they do not constitute a blockchain.
"""

from __future__ import annotations

import hmac
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrity_trace import EvidenceIntegrityTrace
from app.models.trace_types import TraceStatus, TraceType
from app.services.trace_canonicalization import canonical_json, sha256_hex

logger = logging.getLogger(__name__)

# Required top-level keys of a canonical payload.
_REQUIRED_PAYLOAD_KEYS = ("hash_domain", "schema", "envelope", "content")
# Required envelope identity fields.
_REQUIRED_ENVELOPE_KEYS = (
    "trace_id",
    "payment_id",
    "evaluated_at",
    "methodology_version",
    "status",
)


class TraceVerificationService:
    """Internal verification service for decision-trace cryptography."""

    # ------------------------------------------------------------------
    # Single-trace verification
    # ------------------------------------------------------------------

    @classmethod
    def verify_trace_integrity(cls, db: Session, trace_id: str) -> dict:
        """
        Verify one trace's cryptographic integrity.

        Returns a safe result dict. Internal cryptographic implementation
        details beyond algorithm name are not exposed.
        """
        trace = cls._get_trace(db, trace_id)
        if trace is None:
            return {
                "trace_id": trace_id,
                "status": "NOT_FOUND",
                "message": "Trace does not exist.",
            }

        if trace.status == TraceStatus.EVALUATION_STARTED or trace.trace_hash is None:
            return {
                "trace_id": trace_id,
                "status": "VERIFICATION_UNAVAILABLE",
                "trace_status": trace.status,
                "message": (
                    "Trace is not finalized; no hash has been generated yet. "
                    "Verification cannot claim VALID."
                ),
            }

        payload = trace.canonical_payload
        structural_error = cls._structural_check(payload)
        if structural_error is not None:
            return {
                "trace_id": trace_id,
                "status": "INVALID",
                "trace_status": trace.status,
                "hash_algorithm": trace.hash_algorithm,
                "reason": f"Canonical payload structure incomplete: {structural_error}",
            }

        recomputed = sha256_hex(canonical_json(payload))
        matches = hmac.compare_digest(recomputed, trace.trace_hash)

        result = {
            "trace_id": trace_id,
            "trace_status": trace.status,
            "hash_algorithm": trace.hash_algorithm,
            "canonicalization_version": trace.canonicalization_version,
        }
        if matches:
            result["status"] = "VALID"
            result["message"] = "Stored hash matches the canonical payload."
        else:
            result["status"] = "INVALID"
            result["message"] = (
                "Stored hash does NOT match the canonical payload — "
                "trace contents were modified after finalization."
            )

        logger.info(
            "Trace integrity verified",
            extra={
                "trace_id": trace_id,
                "payment_id": trace.payment_id,
                "hash_verification_status": result["status"],
            },
        )
        return result

    # ------------------------------------------------------------------
    # Hash-chain verification
    # ------------------------------------------------------------------

    @classmethod
    def verify_trace_chain(cls, db: Session, payment_id: str) -> dict:
        """
        Verify the per-payment EVALUATION hash chain.

        For every finalized EVALUATION trace, ordered by
        (evaluated_at, internal_id):
          - recompute the hash from the stored canonical payload
          - require previous_trace_hash == predecessor's stored trace_hash
          - require previous_trace_id == predecessor's trace_id

        The FIRST trace legitimately has previous_trace_hash = NULL.
        REPLAY traces are not part of the evaluation chain.
        """
        traces = list(
            db.execute(
                select(EvidenceIntegrityTrace)
                .where(
                    EvidenceIntegrityTrace.payment_id == payment_id,
                    EvidenceIntegrityTrace.trace_type == TraceType.EVALUATION,
                    EvidenceIntegrityTrace.status.in_(
                        [TraceStatus.COMPLETED, TraceStatus.FAILED]
                    ),
                )
                .order_by(
                    EvidenceIntegrityTrace.evaluated_at.asc(),
                    EvidenceIntegrityTrace.internal_id.asc(),
                )
            ).scalars().all()
        )

        if not traces:
            return {
                "payment_id": payment_id,
                "status": "NO_TRACES",
                "verified_count": 0,
                "message": "No finalized evaluation traces exist for this payment.",
            }

        problems: list[dict] = []
        for index, trace in enumerate(traces):
            # 1. Stored hash must match recomputed payload hash.
            if trace.canonical_payload is None or trace.trace_hash is None:
                problems.append(
                    {
                        "position": index,
                        "trace_id": trace.trace_id,
                        "issue": "MISSING_HASH_OR_PAYLOAD",
                    }
                )
                continue
            recomputed = sha256_hex(canonical_json(trace.canonical_payload))
            if not hmac.compare_digest(recomputed, trace.trace_hash):
                problems.append(
                    {
                        "position": index,
                        "trace_id": trace.trace_id,
                        "issue": "HASH_MISMATCH",
                        "detail": "Recomputed hash differs from stored trace_hash.",
                    }
                )

            # 2. Linkage to predecessor.
            if index == 0:
                if trace.previous_trace_hash is not None:
                    problems.append(
                        {
                            "position": 0,
                            "trace_id": trace.trace_id,
                            "issue": "DANGLING_PREVIOUS_HASH",
                            "detail": (
                                "First chain link must have previous_trace_hash NULL."
                            ),
                        }
                    )
            else:
                predecessor = traces[index - 1]
                if trace.previous_trace_hash != predecessor.trace_hash:
                    problems.append(
                        {
                            "position": index,
                            "trace_id": trace.trace_id,
                            "issue": "BROKEN_LINK_HASH",
                            "detail": (
                                "previous_trace_hash does not equal the "
                                "predecessor's stored trace_hash."
                            ),
                        }
                    )
                if trace.previous_trace_id != predecessor.trace_id:
                    problems.append(
                        {
                            "position": index,
                            "trace_id": trace.trace_id,
                            "issue": "BROKEN_LINK_ID",
                            "detail": (
                                "previous_trace_id does not equal the "
                                "predecessor's trace_id."
                            ),
                        }
                    )

        result = {
            "payment_id": payment_id,
            "verified_count": len(traces),
            "chain_start_trace_id": traces[0].trace_id if traces else None,
            "problems": problems,
        }
        if problems:
            result["status"] = "CHAIN_INVALID"
            result["message"] = (
                f"{len(problems)} integrity problem(s) detected in the hash chain."
            )
        elif len(traces) == 1:
            result["status"] = "CHAIN_START"
            result["message"] = (
                "Single-link chain: first trace verified, no predecessor exists."
            )
        else:
            result["status"] = "CHAIN_VALID"
            result["message"] = (
                f"All {len(traces)} links verified; every trace connects "
                "cryptographically to its predecessor."
            )

        logger.info(
            "Trace chain verified",
            extra={
                "payment_id": payment_id,
                "hash_verification_status": result["status"],
                "verified_count": len(traces),
            },
        )
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_trace(db: Session, trace_id: str) -> EvidenceIntegrityTrace | None:
        return db.execute(
            select(EvidenceIntegrityTrace).where(
                EvidenceIntegrityTrace.trace_id == trace_id
            )
        ).scalar_one_or_none()

    @staticmethod
    def _structural_check(payload) -> str | None:
        """Return an error string when the payload structure is incomplete."""
        if not isinstance(payload, dict):
            return "payload is not an object"
        for key in _REQUIRED_PAYLOAD_KEYS:
            if key not in payload:
                return f"missing '{key}' section"
        envelope = payload.get("envelope")
        if not isinstance(envelope, dict):
            return "'envelope' is not an object"
        for key in _REQUIRED_ENVELOPE_KEYS:
            if key not in envelope:
                return f"envelope missing '{key}'"
        return None
