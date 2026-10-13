"""RollyPay webhook endpoint for signed, idempotent payment callbacks."""

import asyncio
import json
import logging
import os

from aiohttp import web

from bot.database.billing import (
    apply_recurring_charge,
    complete_initial_payment,
    get_initial_order,
    get_user_for_provider_subscription,
    mark_initial_payment_failed,
)
from bot.utils.payments import (
    INITIAL_AMOUNT_RUB,
    RECURRING_AMOUNT_RUB,
    TERMINAL_ID,
    check_invoice_status,
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)


async def handle_rollypay_webhook(request: web.Request) -> web.Response:
    raw_body = await request.read()
    signature = request.headers.get("X-Signature", "")
    timestamp = request.headers.get("X-Timestamp", "")
    if not verify_webhook_signature(raw_body, timestamp, signature):
        logger.warning("Rejected RollyPay webhook: invalid signature")
        return web.Response(status=403, text="Invalid signature")

    try:
        event = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return web.Response(status=400, text="Invalid JSON")

    event_type = event.get("event_type")
    payment_id = event.get("payment_id")
    if not payment_id:
        return web.Response(status=400, text="Missing payment_id")

    # Ignore non-payment events, but acknowledge them so RollyPay doesn't retry forever.
    if event_type != "payment.paid":
        if event_type in {"payment.canceled", "payment.expired"}:
            order_id = str(event.get("order_id") or "")
            if order_id:
                await mark_initial_payment_failed(order_id, str(payment_id), event_type.removeprefix("payment."))
        if event_type in {"payment.refunded", "payment.chargeback"}:
            logger.error(
                "RollyPay reported a late %s for payment %s; manual reconciliation may be required",
                event_type, payment_id,
            )
        return web.Response(status=200, text="OK")

    payment = await asyncio.to_thread(check_invoice_status, str(payment_id))
    if not payment:
        # Ask RollyPay to retry when the verification API is temporarily unavailable.
        return web.Response(status=503, text="Payment verification unavailable")
    if payment.get("status") != "paid":
        return web.Response(status=200, text="Payment is not paid")

    currency = str(payment.get("currency") or payment.get("payment_currency") or "")
    if currency != "RUB":
        logger.error("Rejected non-RUB payment callback: %s", payment_id)
        return web.Response(status=200, text="Unexpected currency")
    if TERMINAL_ID and payment.get("terminal_id") and payment["terminal_id"] != TERMINAL_ID:
        logger.error("Rejected payment %s from unexpected terminal", payment_id)
        return web.Response(status=200, text="Unexpected terminal")

    # Initial one-time payment: mark it paid and grant the first three days once.
    order_id = str(payment.get("order_id") or event.get("order_id") or "")
    initial_order = await get_initial_order(order_id) if order_id else None
    if initial_order:
        try:
            amount = round(float(payment.get("amount", 0)), 2)
        except (TypeError, ValueError):
            amount = 0
        saved_payment_id = initial_order.get("payment_id")
        if saved_payment_id and saved_payment_id != str(payment_id):
            logger.error("RollyPay order %s received an unexpected payment id", order_id)
            return web.Response(status=200, text="Unexpected payment id")
        if (
            initial_order["purpose"] == "initial"
            and amount == INITIAL_AMOUNT_RUB
            and initial_order["order_id"] == order_id
        ):
            await complete_initial_payment(order_id, str(payment_id))
            return web.Response(status=200, text="OK")

    # Recurring payment: provider's payment resource is authoritative for subscription_id.
    subscription_id = payment.get("subscription_id")
    payment_method = payment.get("payment_method")
    try:
        amount = round(float(payment.get("amount", 0)), 2)
    except (TypeError, ValueError):
        amount = 0
    if (
        not subscription_id
        or payment_method != "sbp_recurrent"
        or amount != RECURRING_AMOUNT_RUB
    ):
        logger.warning("Paid RollyPay payment %s is not a recognized recurring VIP charge", payment_id)
        return web.Response(status=200, text="Not a recurring VIP charge")

    user_id = await get_user_for_provider_subscription(str(subscription_id))
    if user_id is None:
        logger.error(
            "No local user mapping for RollyPay subscription %s (payment %s)",
            subscription_id, payment_id,
        )
        return web.Response(status=503, text="Subscription mapping unavailable")

    await apply_recurring_charge(str(payment_id), user_id, amount)
    return web.Response(status=200, text="OK")


def create_webhook_app() -> web.Application:
    app = web.Application(client_max_size=64 * 1024)
    app.router.add_post("/webhooks/rollypay", handle_rollypay_webhook)
    return app
