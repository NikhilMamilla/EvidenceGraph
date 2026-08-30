"""
Razorpay REST API client.

Only implements what Phase 2 requires:
  - fetch_payment(payment_id)   — retrieve payment details by ID
  - fetch_order_payments(order_id) — retrieve payments for an order

Uses httpx with timeouts. Credentials come from Settings — never hardcoded.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

RAZORPAY_API_BASE = "https://api.razorpay.com/v1"
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _get_auth() -> tuple[str, str]:
    settings = get_settings()
    return (settings.razorpay_key_id, settings.razorpay_key_secret)


def fetch_payment(payment_id: str) -> dict[str, Any]:
    """
    Fetch a single payment by ID from the Razorpay API.
    Raises httpx.HTTPError on failure.
    """
    auth = _get_auth()
    url = f"{RAZORPAY_API_BASE}/payments/{payment_id}"
    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.get(url, auth=auth)
    if response.status_code == 401:
        logger.error("Razorpay API authentication failed for payment fetch")
        response.raise_for_status()
    if response.status_code == 404:
        logger.warning("Payment not found in Razorpay: %s", payment_id)
        response.raise_for_status()
    response.raise_for_status()
    data: dict[str, Any] = response.json()
    logger.info("Razorpay payment fetched", extra={"payment_id": payment_id})
    return data


def fetch_order_payments(order_id: str) -> list[dict[str, Any]]:
    """
    Fetch all payments for an order from the Razorpay API.
    Returns list of payment objects.
    """
    auth = _get_auth()
    url = f"{RAZORPAY_API_BASE}/orders/{order_id}/payments"
    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.get(url, auth=auth)
    response.raise_for_status()
    data: dict[str, Any] = response.json()
    items: list[dict[str, Any]] = data.get("items", [])
    logger.info(
        "Razorpay order payments fetched",
        extra={"order_id": order_id, "count": len(items)},
    )
    return items
