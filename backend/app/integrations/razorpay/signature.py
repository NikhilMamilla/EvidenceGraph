"""
Razorpay webhook signature verification.

Razorpay uses HMAC-SHA256 with the webhook secret as the key.
The raw request body bytes must be used — never re-serialized JSON.

Reference: https://razorpay.com/docs/webhooks/validate-test/
"""

from __future__ import annotations

import hashlib
import hmac
import logging

logger = logging.getLogger(__name__)


def verify_webhook_signature(
    raw_body: bytes,
    signature_header: str,
    webhook_secret: str,
) -> bool:
    """
    Return True if the X-Razorpay-Signature header matches the HMAC-SHA256
    of the raw body using the webhook secret.

    Never logs the secret or the full body.
    """
    try:
        expected = hmac.new(
            webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature_header)
    except Exception as exc:
        logger.warning("Signature verification error: %s", type(exc).__name__)
        return False
