"""
Phase 10 — Canonical serialization and SHA-256 trace hashing.

This module defines the EXACT byte-level representation that is hashed for
every Evidence Integrity Decision Trace. Hashing arbitrary JSON is forbidden:
key ordering, float formatting, and timestamp rendering must be pinned down so
that the same logical trace content always produces the same digest.

Canonical form — CG-1.0
-----------------------
Objects      keys sorted lexicographically (Unicode code point order);
             duplicate keys impossible (input comes from Python dicts)
Arrays       element order preserved (semantic order, not sorted)
Strings      JSON string escaping; non-ASCII characters escaped (ensure_ascii)
Timestamps   datetime objects rendered as RFC3339 UTC with microseconds:
                 YYYY-MM-DDTHH:MM:SS.ffffffZ   (naive input assumed UTC)
Integers     decimal digits as-is (arbitrary precision)
Floats       finite values only; integral values normalized to integers;
             non-integral via shortest round-trip repr (Python repr(float))
Booleans     true / false
Null         null (explicitly preserved — never dropped)
Separators   ',' between items, ':' after keys, no whitespace
Encoding     UTF-8 bytes of the resulting text are hashed

Non-finite floats (NaN, +/-Infinity) raise CanonicalizationError rather than
being emitted as non-standard JSON tokens.

What is hashed (trace identity + audit content)
-----------------------------------------------
The canonical payload stored in evidence_integrity_traces.canonical_payload:

    {
      "hash_domain":  "evidencegraph.integrity_trace.v1",
      "schema":       "<TRACE_SCHEMA_VERSION>",
      "envelope": {
          trace_id, trace_type, original_trace_id, payment_id,
          evaluated_at, methodology_version, methodology_snapshot_hash,
          status, previous_trace_hash
      },
      "content": { ...evaluation context, evidence inputs/exclusions,
                   measurements, structure, corroboration, consistency,
                   rule executions, intermediate results, final result,
                   limitations, explanation ... }
    }

Explicitly NOT hashed:
    - created_at / finalized_at (DB-generated mutable metadata)
    - trigger (request provenance metadata, not audit content)
    - internal_id (database surrogate key)
    - request IDs, query timings, transient logging metadata

Replay comparison compares ONLY the "content" object; envelope fields such as
previous_trace_hash legitimately differ when new traces join the chain.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

from app.models.trace_types import CANONICALIZATION_VERSION, HASH_ALGORITHM


class CanonicalizationError(ValueError):
    """Raised when a value cannot be represented in canonical form."""


# ---------------------------------------------------------------------------
# Canonical value normalization
# ---------------------------------------------------------------------------

def _canonicalize_datetime(value: datetime) -> str:
    """Render any datetime as an RFC3339 UTC string with microsecond precision."""
    if value.tzinfo is None:
        # Naive datetimes are interpreted as UTC by convention in this codebase.
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def canonicalize(value: Any) -> Any:
    """
    Recursively normalize a Python value into its canonical representation.

    Returns plain JSON-compatible Python structures (dict/list/str/int/float/
    bool/None) ready for deterministic serialization.
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, datetime):
        return _canonicalize_datetime(value)
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError(
                f"Non-finite float cannot be canonically serialized: {value!r}"
            )
        if value.is_integer():
            # Normalize e.g. 2.0 → 2 so identical quantities always match.
            # Non-integral floats stay numeric: json.dumps renders them via
            # shortest round-trip repr, which is deterministic in CPython,
            # and the normalization itself is idempotent for storage.
            return int(value)
        return value
    if isinstance(value, dict):
        result = {}
        for key in sorted(value.keys(), key=lambda k: str(k)):
            if not isinstance(key, str):
                raise CanonicalizationError(
                    f"Canonical objects require string keys, got {type(key)!r}"
                )
            result[key] = canonicalize(value[key])
        return result
    if isinstance(value, (list, tuple)):
        return [canonicalize(item) for item in value]
    if hasattr(value, "__dict__"):
        # Defensive fallback: ORM rows or dataclasses must never leak here.
        raise CanonicalizationError(
            f"Value of type {type(value).__name__} must be converted to plain "
            "JSON-compatible structures before canonical serialization."
        )
    raise CanonicalizationError(
        f"Type {type(value).__name__} has no canonical representation."
    )


def canonical_json(payload: Any) -> str:
    """Serialize a value to canonical JSON text (CG-1.0)."""
    normalized = canonicalize(payload)
    return json.dumps(
        normalized,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_hex(canonical_text: str) -> str:
    """Return the SHA-256 hex digest of the UTF-8 encoding of canonical text."""
    return hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()


def canonical_hash(payload: Any) -> tuple[str, str]:
    """
    Canonicalize and hash a payload.

    Returns (canonical_json_text, sha256_hex_digest). The canonicalized
    structure returned implicitly through the text is what must be persisted
    so that re-hashing the stored payload reproduces the identical digest.
    """
    text = canonical_json(payload)
    return text, sha256_hex(text)


def canonical_payload_for_storage(payload: Any) -> dict:
    """
    Normalize a payload into its canonical structure for persistence.

    Datetimes become canonical strings; the stored JSONB is exactly the
    structure whose canonical serialization produced trace_hash — making
    verification a faithful recomputation.
    """
    normalized = canonicalize(payload)
    if not isinstance(normalized, dict):
        raise CanonicalizationError("Trace payloads must be objects at top level.")
    return normalized


# ---------------------------------------------------------------------------
# Methodology snapshot hashing
# ---------------------------------------------------------------------------

def methodology_snapshot_payload(describe: dict) -> dict:
    """Build the canonical methodology snapshot stored inside every trace."""
    return {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "description": describe,
    }


def methodology_snapshot_hash(describe: dict) -> str:
    """Deterministic SHA-256 over the canonical methodology description."""
    _, digest = canonical_hash(methodology_snapshot_payload(describe))
    return digest
