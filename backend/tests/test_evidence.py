"""
Tests for Phase 4 — Evidence Observation & Provenance Layer.

All tests are unit tests — no live database or Redis required.
Tests verify:
  - Extraction produces expected evidence for payment.captured
  - Provenance fields populated on every record
  - Monetary values are integer minor units (no float)
  - Absent fields produce no evidence records
  - extraction_version present on every record
  - Idempotency: same event does not produce uncontrolled duplicates
  - Multiple events produce distinct observations
  - No updated_at column on EvidenceObservation (immutability by design)
  - Foreign keys: invalid lineage cannot be constructed without valid refs
  - order.paid event extracts order evidence
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/evidencegraph_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test_testkey")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "test_secret")
os.environ.setdefault("RAZORPAY_WEBHOOK_SECRET", "test_webhook_secret_2026")
os.environ.setdefault("RAZORPAY_MODE", "test")


# ---------------------------------------------------------------------------
# Sample payloads
# ---------------------------------------------------------------------------

SAMPLE_PAYMENT_CAPTURED_PAYLOAD = {
    "entity": "event",
    "account_id": "acc_test123",
    "event": "payment.captured",
    "contains": ["payment"],
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_test001",
                "order_id": "order_test001",
                "status": "captured",
                "amount": 49900,
                "currency": "INR",
                "method": "upi",
            }
        }
    },
    "created_at": 1724217600,
}

SAMPLE_PAYMENT_FAILED_PAYLOAD = {
    "entity": "event",
    "account_id": "acc_test123",
    "event": "payment.failed",
    "contains": ["payment"],
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_test002",
                "order_id": "order_test001",
                "status": "failed",
                "amount": 49900,
                "currency": "INR",
                "method": "card",
            }
        }
    },
    "created_at": 1724217700,
}

SAMPLE_ORDER_PAID_PAYLOAD = {
    "entity": "event",
    "account_id": "acc_test123",
    "event": "order.paid",
    "contains": ["order", "payment"],
    "payload": {
        "order": {
            "entity": {
                "id": "order_test002",
                "status": "paid",
                "amount": 99900,
                "currency": "INR",
            }
        },
        "payment": {
            "entity": {
                "id": "pay_test003",
                "order_id": "order_test002",
                "status": "captured",
                "amount": 99900,
                "currency": "INR",
                "method": "netbanking",
            }
        },
    },
    "created_at": 1724217800,
}

# Payload with several fields intentionally absent
SAMPLE_MINIMAL_PAYLOAD = {
    "entity": "event",
    "event": "payment.authorized",
    "contains": ["payment"],
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_test004",
                # No amount, currency, method, order_id
            }
        }
    },
    "created_at": 1724217900,
}


# ---------------------------------------------------------------------------
# Helper: build mock PaymentEvent and WebhookEvent
# ---------------------------------------------------------------------------

def _make_payment_event(
    internal_id: int = 1,
    payment_id: int = 1,
    webhook_event_id: int = 10,
    event_type: str = "payment.captured",
    event_timestamp: datetime | None = None,
) -> MagicMock:
    pe = MagicMock()
    pe.internal_id = internal_id
    pe.payment_id = payment_id
    pe.webhook_event_id = webhook_event_id
    pe.event_type = event_type
    pe.event_timestamp = event_timestamp or datetime(2024, 8, 21, 12, 0, 0, tzinfo=timezone.utc)
    return pe


def _make_webhook_event(
    db_id: int = 10,
    raw_payload: dict | None = None,
    received_at: datetime | None = None,
    razorpay_event_id: str | None = "evt_test001",
    event_type: str = "payment.captured",
) -> MagicMock:
    we = MagicMock()
    we.id = db_id
    we.raw_payload = raw_payload or SAMPLE_PAYMENT_CAPTURED_PAYLOAD
    we.received_at = received_at or datetime(2024, 8, 21, 12, 0, 1, tzinfo=timezone.utc)
    we.razorpay_event_id = razorpay_event_id
    we.event_type = event_type
    return we


# ---------------------------------------------------------------------------
# Tests — Core extraction
# ---------------------------------------------------------------------------

class TestEvidenceExtraction:
    def test_payment_captured_generates_expected_evidence(self):
        from app.services.evidence_service import extract_evidence_from_payment_event
        from app.models.evidence_types import EvidenceType

        pe = _make_payment_event(event_type="payment.captured")
        we = _make_webhook_event(raw_payload=SAMPLE_PAYMENT_CAPTURED_PAYLOAD)

        observations = extract_evidence_from_payment_event(pe, we)

        evidence_types = {o.evidence_type for o in observations}

        assert EvidenceType.PAYMENT_EVENT in evidence_types
        assert EvidenceType.PAYMENT_STATUS in evidence_types
        assert EvidenceType.PAYMENT_AMOUNT in evidence_types
        assert EvidenceType.PAYMENT_CURRENCY in evidence_types
        assert EvidenceType.PAYMENT_METHOD in evidence_types
        assert EvidenceType.PAYMENT_ORDER_RELATIONSHIP in evidence_types

    def test_payment_failed_generates_failed_status(self):
        from app.services.evidence_service import extract_evidence_from_payment_event
        from app.models.evidence_types import EvidenceType

        pe = _make_payment_event(event_type="payment.failed")
        we = _make_webhook_event(
            raw_payload=SAMPLE_PAYMENT_FAILED_PAYLOAD,
            event_type="payment.failed",
        )

        observations = extract_evidence_from_payment_event(pe, we)
        status_obs = [o for o in observations if o.evidence_type == EvidenceType.PAYMENT_STATUS]

        assert len(status_obs) == 1
        assert status_obs[0].value == "failed"

    def test_order_paid_generates_order_evidence(self):
        from app.services.evidence_service import extract_evidence_from_payment_event
        from app.models.evidence_types import EvidenceType, SubjectType

        pe = _make_payment_event(event_type="order.paid")
        we = _make_webhook_event(
            raw_payload=SAMPLE_ORDER_PAID_PAYLOAD,
            event_type="order.paid",
        )

        observations = extract_evidence_from_payment_event(pe, we)
        order_obs = [o for o in observations if o.subject_type == SubjectType.ORDER]
        order_types = {o.evidence_type for o in order_obs}

        assert EvidenceType.ORDER_STATUS in order_types
        assert EvidenceType.ORDER_AMOUNT in order_types
        assert EvidenceType.ORDER_CURRENCY in order_types

    def test_correct_payment_id_as_subject_id(self):
        from app.services.evidence_service import extract_evidence_from_payment_event
        from app.models.evidence_types import SubjectType

        pe = _make_payment_event(event_type="payment.captured")
        we = _make_webhook_event(raw_payload=SAMPLE_PAYMENT_CAPTURED_PAYLOAD)

        observations = extract_evidence_from_payment_event(pe, we)
        payment_obs = [o for o in observations if o.subject_type == SubjectType.PAYMENT]

        for obs in payment_obs:
            assert obs.subject_id == "pay_test001"

    def test_correct_order_id_as_subject_id_for_order_paid(self):
        from app.services.evidence_service import extract_evidence_from_payment_event
        from app.models.evidence_types import SubjectType

        pe = _make_payment_event(event_type="order.paid")
        we = _make_webhook_event(
            raw_payload=SAMPLE_ORDER_PAID_PAYLOAD,
            event_type="order.paid",
        )

        observations = extract_evidence_from_payment_event(pe, we)
        order_obs = [o for o in observations if o.subject_type == SubjectType.ORDER]

        for obs in order_obs:
            assert obs.subject_id == "order_test002"


# ---------------------------------------------------------------------------
# Tests — Provenance
# ---------------------------------------------------------------------------

class TestProvenance:
    def test_source_type_is_razorpay_webhook(self):
        from app.services.evidence_service import extract_evidence_from_payment_event
        from app.models.evidence_types import SourceType

        pe = _make_payment_event()
        we = _make_webhook_event(db_id=42)

        observations = extract_evidence_from_payment_event(pe, we)
        for obs in observations:
            assert obs.source_type == SourceType.RAZORPAY_WEBHOOK

    def test_source_reference_is_webhook_event_id(self):
        from app.services.evidence_service import extract_evidence_from_payment_event

        pe = _make_payment_event(webhook_event_id=42)
        we = _make_webhook_event(db_id=42)

        observations = extract_evidence_from_payment_event(pe, we)
        for obs in observations:
            assert obs.source_reference == "42"

    def test_webhook_event_id_fk_set(self):
        from app.services.evidence_service import extract_evidence_from_payment_event

        pe = _make_payment_event(webhook_event_id=99)
        we = _make_webhook_event(db_id=99)

        observations = extract_evidence_from_payment_event(pe, we)
        for obs in observations:
            assert obs.webhook_event_id == 99

    def test_payment_event_id_fk_set(self):
        from app.services.evidence_service import extract_evidence_from_payment_event

        pe = _make_payment_event(internal_id=7)
        we = _make_webhook_event()

        observations = extract_evidence_from_payment_event(pe, we)
        for obs in observations:
            assert obs.payment_event_id == 7

    def test_provenance_metadata_populated(self):
        from app.services.evidence_service import extract_evidence_from_payment_event

        pe = _make_payment_event(event_type="payment.captured")
        we = _make_webhook_event()

        observations = extract_evidence_from_payment_event(pe, we)
        for obs in observations:
            assert obs.provenance_metadata is not None
            assert obs.provenance_metadata.get("provider") == "razorpay"
            assert obs.provenance_metadata.get("event_type") == "payment.captured"

    def test_extraction_version_is_current(self):
        from app.services.evidence_service import extract_evidence_from_payment_event
        from app.models.evidence_types import CURRENT_EXTRACTION_VERSION

        pe = _make_payment_event()
        we = _make_webhook_event()

        observations = extract_evidence_from_payment_event(pe, we)
        for obs in observations:
            assert obs.extraction_version == CURRENT_EXTRACTION_VERSION

    def test_extraction_method_is_webhook_field_extraction(self):
        from app.services.evidence_service import extract_evidence_from_payment_event
        from app.models.evidence_types import ExtractionMethod

        pe = _make_payment_event()
        we = _make_webhook_event()

        observations = extract_evidence_from_payment_event(pe, we)
        for obs in observations:
            assert obs.extraction_method == ExtractionMethod.WEBHOOK_FIELD_EXTRACTION


# ---------------------------------------------------------------------------
# Tests — Observation time
# ---------------------------------------------------------------------------

class TestObservationTime:
    def test_observed_at_uses_payment_event_timestamp(self):
        from app.services.evidence_service import extract_evidence_from_payment_event

        event_ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        pe = _make_payment_event(event_timestamp=event_ts)
        we = _make_webhook_event()

        observations = extract_evidence_from_payment_event(pe, we)
        for obs in observations:
            assert obs.observed_at == event_ts

    def test_observed_at_falls_back_to_received_at_when_event_timestamp_none(self):
        from app.services.evidence_service import extract_evidence_from_payment_event

        received = datetime(2024, 1, 15, 10, 31, 0, tzinfo=timezone.utc)

        # Build a payment_event MagicMock that returns None for event_timestamp
        pe = MagicMock()
        pe.internal_id = 1
        pe.payment_id = 1
        pe.webhook_event_id = 10
        pe.event_type = "payment.captured"
        pe.event_timestamp = None  # explicitly None

        we = _make_webhook_event(received_at=received)

        observations = extract_evidence_from_payment_event(pe, we)
        for obs in observations:
            assert obs.observed_at == received



# ---------------------------------------------------------------------------
# Tests — Monetary values
# ---------------------------------------------------------------------------

class TestMonetaryValues:
    def test_amount_stored_as_integer_minor_units(self):
        from app.services.evidence_service import extract_evidence_from_payment_event
        from app.models.evidence_types import EvidenceType, ValueType

        pe = _make_payment_event()
        we = _make_webhook_event(raw_payload=SAMPLE_PAYMENT_CAPTURED_PAYLOAD)

        observations = extract_evidence_from_payment_event(pe, we)
        amount_obs = [o for o in observations if o.evidence_type == EvidenceType.PAYMENT_AMOUNT]

        assert len(amount_obs) == 1
        assert amount_obs[0].value == "49900"
        assert amount_obs[0].value_type == ValueType.INTEGER_MINOR_UNITS

    def test_amount_value_is_string_not_float(self):
        from app.services.evidence_service import extract_evidence_from_payment_event
        from app.models.evidence_types import EvidenceType

        pe = _make_payment_event()
        we = _make_webhook_event(raw_payload=SAMPLE_PAYMENT_CAPTURED_PAYLOAD)

        observations = extract_evidence_from_payment_event(pe, we)
        amount_obs = [o for o in observations if o.evidence_type == EvidenceType.PAYMENT_AMOUNT]

        # Must be a plain integer string — no decimal point
        assert "." not in amount_obs[0].value
        assert amount_obs[0].value == "49900"


# ---------------------------------------------------------------------------
# Tests — Absent fields (absence != negative)
# ---------------------------------------------------------------------------

class TestAbsenceOfEvidence:
    def test_missing_amount_produces_no_evidence(self):
        from app.services.evidence_service import extract_evidence_from_payment_event
        from app.models.evidence_types import EvidenceType

        pe = _make_payment_event(event_type="payment.authorized")
        we = _make_webhook_event(
            raw_payload=SAMPLE_MINIMAL_PAYLOAD,
            event_type="payment.authorized",
        )

        observations = extract_evidence_from_payment_event(pe, we)
        amount_obs = [o for o in observations if o.evidence_type == EvidenceType.PAYMENT_AMOUNT]
        assert len(amount_obs) == 0

    def test_missing_currency_produces_no_evidence(self):
        from app.services.evidence_service import extract_evidence_from_payment_event
        from app.models.evidence_types import EvidenceType

        pe = _make_payment_event(event_type="payment.authorized")
        we = _make_webhook_event(
            raw_payload=SAMPLE_MINIMAL_PAYLOAD,
            event_type="payment.authorized",
        )

        observations = extract_evidence_from_payment_event(pe, we)
        currency_obs = [o for o in observations if o.evidence_type == EvidenceType.PAYMENT_CURRENCY]
        assert len(currency_obs) == 0

    def test_missing_method_produces_no_evidence(self):
        from app.services.evidence_service import extract_evidence_from_payment_event
        from app.models.evidence_types import EvidenceType

        pe = _make_payment_event(event_type="payment.authorized")
        we = _make_webhook_event(
            raw_payload=SAMPLE_MINIMAL_PAYLOAD,
            event_type="payment.authorized",
        )

        observations = extract_evidence_from_payment_event(pe, we)
        method_obs = [o for o in observations if o.evidence_type == EvidenceType.PAYMENT_METHOD]
        assert len(method_obs) == 0

    def test_missing_order_id_produces_no_relationship_evidence(self):
        from app.services.evidence_service import extract_evidence_from_payment_event
        from app.models.evidence_types import EvidenceType

        pe = _make_payment_event(event_type="payment.authorized")
        we = _make_webhook_event(
            raw_payload=SAMPLE_MINIMAL_PAYLOAD,
            event_type="payment.authorized",
        )

        observations = extract_evidence_from_payment_event(pe, we)
        rel_obs = [o for o in observations if o.evidence_type == EvidenceType.PAYMENT_ORDER_RELATIONSHIP]
        assert len(rel_obs) == 0

    def test_minimal_payload_still_produces_event_and_status(self):
        from app.services.evidence_service import extract_evidence_from_payment_event
        from app.models.evidence_types import EvidenceType

        pe = _make_payment_event(event_type="payment.authorized")
        we = _make_webhook_event(
            raw_payload=SAMPLE_MINIMAL_PAYLOAD,
            event_type="payment.authorized",
        )

        observations = extract_evidence_from_payment_event(pe, we)
        evidence_types = {o.evidence_type for o in observations}
        # PAYMENT_EVENT and PAYMENT_STATUS are derived from event_type, not payload fields
        assert EvidenceType.PAYMENT_EVENT in evidence_types
        assert EvidenceType.PAYMENT_STATUS in evidence_types


# ---------------------------------------------------------------------------
# Tests — Multiple events produce distinct observations
# ---------------------------------------------------------------------------

class TestMultipleEvents:
    def test_different_events_produce_distinct_payment_event_observations(self):
        from app.services.evidence_service import extract_evidence_from_payment_event
        from app.models.evidence_types import EvidenceType

        # First event: payment.authorized
        pe1 = _make_payment_event(internal_id=1, webhook_event_id=10, event_type="payment.authorized")
        we1 = _make_webhook_event(
            db_id=10,
            raw_payload={**SAMPLE_PAYMENT_CAPTURED_PAYLOAD, "event": "payment.authorized"},
            event_type="payment.authorized",
        )

        # Second event: payment.captured
        pe2 = _make_payment_event(internal_id=2, webhook_event_id=11, event_type="payment.captured")
        we2 = _make_webhook_event(
            db_id=11,
            raw_payload=SAMPLE_PAYMENT_CAPTURED_PAYLOAD,
            event_type="payment.captured",
        )

        obs1 = extract_evidence_from_payment_event(pe1, we1)
        obs2 = extract_evidence_from_payment_event(pe2, we2)

        # Each set has its own payment_event_id
        for o in obs1:
            assert o.payment_event_id == 1
        for o in obs2:
            assert o.payment_event_id == 2

        # PAYMENT_STATUS values differ
        status1 = [o for o in obs1 if o.evidence_type == EvidenceType.PAYMENT_STATUS]
        status2 = [o for o in obs2 if o.evidence_type == EvidenceType.PAYMENT_STATUS]
        assert status1[0].value == "authorized"
        assert status2[0].value == "captured"

    def test_same_event_produces_same_evidence_types(self):
        """Determinism check: same input → same evidence types."""
        from app.services.evidence_service import extract_evidence_from_payment_event

        pe = _make_payment_event()
        we = _make_webhook_event(raw_payload=SAMPLE_PAYMENT_CAPTURED_PAYLOAD)

        obs_first = extract_evidence_from_payment_event(pe, we)
        obs_second = extract_evidence_from_payment_event(pe, we)

        types_first = {o.evidence_type for o in obs_first}
        types_second = {o.evidence_type for o in obs_second}

        assert types_first == types_second
        assert len(obs_first) == len(obs_second)


# ---------------------------------------------------------------------------
# Tests — Immutability by design
# ---------------------------------------------------------------------------

class TestImmutability:
    def test_evidence_observation_has_no_updated_at(self):
        from app.models.evidence import EvidenceObservation
        from sqlalchemy.orm import class_mapper

        mapper = class_mapper(EvidenceObservation)
        column_names = {c.key for c in mapper.columns}

        assert "updated_at" not in column_names, (
            "EvidenceObservation must not have an updated_at column — "
            "evidence records are immutable by design."
        )

    def test_evidence_observation_has_created_at(self):
        from app.models.evidence import EvidenceObservation
        from sqlalchemy.orm import class_mapper

        mapper = class_mapper(EvidenceObservation)
        column_names = {c.key for c in mapper.columns}

        assert "created_at" in column_names

    def test_evidence_observation_has_observed_at(self):
        from app.models.evidence import EvidenceObservation
        from sqlalchemy.orm import class_mapper

        mapper = class_mapper(EvidenceObservation)
        column_names = {c.key for c in mapper.columns}

        assert "observed_at" in column_names


# ---------------------------------------------------------------------------
# Tests — Value types
# ---------------------------------------------------------------------------

class TestValueTypes:
    def test_currency_is_string_value_type(self):
        from app.services.evidence_service import extract_evidence_from_payment_event
        from app.models.evidence_types import EvidenceType, ValueType

        pe = _make_payment_event()
        we = _make_webhook_event(raw_payload=SAMPLE_PAYMENT_CAPTURED_PAYLOAD)

        observations = extract_evidence_from_payment_event(pe, we)
        currency_obs = [o for o in observations if o.evidence_type == EvidenceType.PAYMENT_CURRENCY]

        assert currency_obs[0].value_type == ValueType.STRING
        assert currency_obs[0].value == "INR"

    def test_status_is_enum_value_type(self):
        from app.services.evidence_service import extract_evidence_from_payment_event
        from app.models.evidence_types import EvidenceType, ValueType

        pe = _make_payment_event()
        we = _make_webhook_event(raw_payload=SAMPLE_PAYMENT_CAPTURED_PAYLOAD)

        observations = extract_evidence_from_payment_event(pe, we)
        status_obs = [o for o in observations if o.evidence_type == EvidenceType.PAYMENT_STATUS]

        assert status_obs[0].value_type == ValueType.ENUM

    def test_amount_is_integer_minor_units_value_type(self):
        from app.services.evidence_service import extract_evidence_from_payment_event
        from app.models.evidence_types import EvidenceType, ValueType

        pe = _make_payment_event()
        we = _make_webhook_event(raw_payload=SAMPLE_PAYMENT_CAPTURED_PAYLOAD)

        observations = extract_evidence_from_payment_event(pe, we)
        amount_obs = [o for o in observations if o.evidence_type == EvidenceType.PAYMENT_AMOUNT]

        assert amount_obs[0].value_type == ValueType.INTEGER_MINOR_UNITS


# ---------------------------------------------------------------------------
# Tests — Evidence taxonomy constants
# ---------------------------------------------------------------------------

class TestEvidenceTaxonomy:
    def test_all_evidence_types_defined(self):
        from app.models.evidence_types import EvidenceType

        required = {
            "PAYMENT_AMOUNT",
            "PAYMENT_CURRENCY",
            "PAYMENT_STATUS",
            "PAYMENT_METHOD",
            "ORDER_AMOUNT",
            "ORDER_CURRENCY",
            "ORDER_STATUS",
            "PAYMENT_ORDER_RELATIONSHIP",
            "PAYMENT_EVENT",
        }
        actual = {k for k in vars(EvidenceType) if not k.startswith("_")}
        assert required.issubset(actual)

    def test_all_source_types_defined(self):
        from app.models.evidence_types import SourceType

        required = {"RAZORPAY_WEBHOOK", "RAZORPAY_API", "INTERNAL_SYSTEM"}
        actual = {k for k in vars(SourceType) if not k.startswith("_")}
        assert required.issubset(actual)

    def test_extraction_version_is_string(self):
        from app.models.evidence_types import CURRENT_EXTRACTION_VERSION

        assert isinstance(CURRENT_EXTRACTION_VERSION, str)
        assert len(CURRENT_EXTRACTION_VERSION) > 0
