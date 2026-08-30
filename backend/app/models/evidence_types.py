"""
Evidence taxonomy constants — Phase 4.

These are plain Python string constants, NOT database enum types.
Using plain strings avoids painful Alembic migrations when new types
are added in future phases.

All values stored in the database must come from these classes.
"""

from __future__ import annotations


class EvidenceType:
    """What was observed."""

    PAYMENT_AMOUNT = "PAYMENT_AMOUNT"
    """The monetary amount of a payment, in minor currency units."""

    PAYMENT_CURRENCY = "PAYMENT_CURRENCY"
    """The ISO 4217 currency code of a payment."""

    PAYMENT_STATUS = "PAYMENT_STATUS"
    """The status of a payment at the time of the event (e.g. captured, failed)."""

    PAYMENT_METHOD = "PAYMENT_METHOD"
    """The payment method type (e.g. upi, card, netbanking, wallet)."""

    ORDER_AMOUNT = "ORDER_AMOUNT"
    """The monetary amount of an order, in minor currency units."""

    ORDER_CURRENCY = "ORDER_CURRENCY"
    """The ISO 4217 currency code of an order."""

    ORDER_STATUS = "ORDER_STATUS"
    """The status of an order at the time of the event (e.g. paid, created)."""

    PAYMENT_ORDER_RELATIONSHIP = "PAYMENT_ORDER_RELATIONSHIP"
    """An observed association between a payment and an order."""

    PAYMENT_EVENT = "PAYMENT_EVENT"
    """The occurrence of a specific payment lifecycle event."""


class SourceType:
    """Where the evidence came from."""

    RAZORPAY_WEBHOOK = "RAZORPAY_WEBHOOK"
    """Evidence extracted from a verified Razorpay webhook event."""

    RAZORPAY_API = "RAZORPAY_API"
    """Evidence fetched directly from the Razorpay REST API."""

    INTERNAL_SYSTEM = "INTERNAL_SYSTEM"
    """Evidence derived internally by EvidenceGraph (not from a provider)."""


class ValueType:
    """How the evidence value should be interpreted."""

    INTEGER_MINOR_UNITS = "INTEGER_MINOR_UNITS"
    """Integer representing a monetary amount in the smallest currency unit (e.g. paise)."""

    STRING = "STRING"
    """Plain text string value."""

    ENUM = "ENUM"
    """A value from a controlled vocabulary (e.g. payment status)."""

    BOOLEAN = "BOOLEAN"
    """True or false."""


class SubjectType:
    """What entity the evidence describes."""

    PAYMENT = "payment"
    """The evidence describes a payment."""

    ORDER = "order"
    """The evidence describes an order."""


class ExtractionMethod:
    """How the evidence was extracted."""

    WEBHOOK_FIELD_EXTRACTION = "WEBHOOK_FIELD_EXTRACTION"
    """Deterministic field extraction from a verified webhook payload."""


# Current version of the extraction logic.
# Increment this when extraction rules change so historical records
# can be identified as having been produced by a specific version.
CURRENT_EXTRACTION_VERSION = "1.0"
