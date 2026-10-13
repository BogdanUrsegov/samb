"""RollyPay one-time and recurring SBP API helpers.

Recurring plans are configured by RollyPay. This module never creates or assumes a
plan: it validates the configured UUID against the terminal's API response.
"""

import hashlib
import hmac
import logging
import os
import uuid
from typing import Any

import requests

logger = logging.getLogger(__name__)
API_KEY = os.getenv("ROLLYPAY_API_KEY", "")
API_BASE_URL = "https://rollypay.io/api/v1"
TERMINAL_ID = os.getenv("ROLLYPAY_TERMINAL_ID", "")
RECURRING_PLAN_ID = os.getenv("ROLLYPAY_RECURRING_PLAN_ID", "")
SIGNING_SECRET = os.getenv("ROLLYPAY_SIGNING_SECRET", "")
RECURRING_PLAN_CONFIRMED = os.getenv("ROLLYPAY_RECURRING_PLAN_CONFIRMED", "").lower() == "true"
INITIAL_AMOUNT_RUB = 17
RECURRING_AMOUNT_RUB = 299


def _send_request(
    method: str,
    endpoint: str,
    payload: dict[str, Any] | None = None,
    *,
    idempotency_key: str | None = None,
) -> dict[str, Any] | None:
    """Make one authenticated request. Every attempt uses a fresh X-Nonce."""
    if not API_KEY:
        logger.error("ROLLYPAY_API_KEY is not configured")
        return None

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
        "X-Nonce": str(uuid.uuid4()),
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key[:128]

    try:
        response = requests.request(
            method=method,
            url=f"{API_BASE_URL}/{endpoint.lstrip('/')}",
            headers=headers,
            json=payload,
            timeout=12,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.warning("RollyPay %s %s failed: %s", method, endpoint, exc)
    except ValueError:
        logger.exception("RollyPay returned invalid JSON for %s %s", method, endpoint)
    return None


def create_invoice(amount: float, order_id: str, comment: str | None = None) -> dict[str, Any] | None:
    """Create a one-time SBP payment. Reusing order_id is safe for retries."""
    payload: dict[str, Any] = {
        "amount": f"{amount:.2f}",
        "payment_currency": "RUB",
        "order_id": order_id,
        "payment_method": "sbp",
        "customer_id": f"tg_{order_id[:20]}",
    }
    if TERMINAL_ID:
        payload["terminal_id"] = TERMINAL_ID
    if comment:
        payload["description"] = comment
    return _send_request("POST", "payments", payload)


def check_invoice_status(payment_id: str) -> dict[str, Any] | None:
    return _send_request("GET", f"payments/{payment_id}")


def get_recurring_plans() -> list[dict[str, Any]] | None:
    if not TERMINAL_ID:
        logger.error("ROLLYPAY_TERMINAL_ID is not configured")
        return None
    result = _send_request("GET", f"subscription-plans?terminal_id={TERMINAL_ID}")
    if result is None:
        return None
    items = result.get("items")
    return items if isinstance(items, list) else None


def create_recurring_subscription(
    user_id: int,
    idempotency_key: str,
) -> dict[str, Any] | None:
    """Create consent link for the already-configured 299 RUB / 3-day plan."""
    if not TERMINAL_ID or not RECURRING_PLAN_ID:
        logger.error("ROLLYPAY_TERMINAL_ID / ROLLYPAY_RECURRING_PLAN_ID is not configured")
        return None
    if not RECURRING_PLAN_CONFIRMED:
        logger.error(
            "Recurring plan is disabled until RollyPay confirms 299 RUB every 3 days; "
            "set ROLLYPAY_RECURRING_PLAN_CONFIRMED=true after verification"
        )
        return None

    plans = get_recurring_plans()
    if plans is None:
        return None
    plan = next((item for item in plans if item.get("id") == RECURRING_PLAN_ID), None)
    if not plan:
        logger.error("Configured recurring plan id is not available for this terminal")
        return None

    amount = plan.get("payer_amount_rub")
    if amount is None or round(float(amount), 2) != RECURRING_AMOUNT_RUB:
        logger.error("Configured recurring plan does not charge exactly 299 RUB")
        return None

    # Reject an obviously incompatible plan. The public plan response may not
    # expose the exact day count, so manual confirmation from RollyPay is required.
    interval = str(plan.get("interval", "")).lower()
    if interval and interval not in {"day", "days", "3_days", "every_3_days"}:
        logger.error("Configured RollyPay plan interval is not a 3-day interval")
        return None
    for key in ("interval_days", "period_days", "interval_count"):
        if key in plan and int(plan[key]) != 3:
            logger.error("Configured RollyPay plan does not have a 3-day interval")
            return None

    payload = {
        "terminal_id": TERMINAL_ID,
        "plan_id": RECURRING_PLAN_ID,
        "payer_id": f"tg_{user_id}",
        "merchant_subscription_ref": f"tg-vip-{user_id}",
        "description": "VIP — 299 RUB every 3 days",
    }
    result = _send_request(
        "POST",
        "subscriptions",
        payload,
        idempotency_key=idempotency_key,
    )
    if result and not (result.get("pay_url") or result.get("redirect_url")):
        logger.error("RollyPay subscription response has no consent URL")
    return result


def get_recurring_subscription(subscription_id: str) -> dict[str, Any] | None:
    return _send_request("GET", f"subscriptions/{subscription_id}")


def stop_recurring_subscription(subscription_id: str) -> dict[str, Any] | None:
    return _send_request("POST", f"subscriptions/{subscription_id}/stop", {})


def verify_webhook_signature(raw_body: bytes, timestamp: str, signature: str) -> bool:
    """Validate RollyPay HMAC-SHA256 over timestamp + '.' + the exact raw body."""
    if not SIGNING_SECRET or not timestamp or not signature:
        return False
    signed_payload = timestamp.encode("utf-8") + b"." + raw_body
    expected = hmac.new(
        SIGNING_SECRET.encode("utf-8"), signed_payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
