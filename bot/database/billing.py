"""Persistence helpers for the 3-day VIP offer and RollyPay recurring billing."""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .models import BillingPayment, ProcessedCharge, RecurringBilling, Subscription
from .session import async_session, sqlite_write_lock

INITIAL_AMOUNT_RUB = 17
RECURRING_AMOUNT_RUB = 299
ACCESS_DAYS = 3


async def create_initial_order(user_id: int, order_id: str) -> str:
    """Persist a stable order id before calling RollyPay (order_id is idempotent)."""
    async with sqlite_write_lock:
        async with async_session() as session:
            async with session.begin():
                existing = await session.scalar(
                    select(BillingPayment).where(
                        BillingPayment.user_id == user_id,
                        BillingPayment.purpose == "initial",
                        BillingPayment.status == "pending",
                    ).order_by(BillingPayment.created_at.desc()).limit(1)
                )
                if existing:
                    return existing.order_id
                session.add(BillingPayment(
                    order_id=order_id,
                    user_id=user_id,
                    amount=INITIAL_AMOUNT_RUB,
                    purpose="initial",
                    status="pending",
                ))
    return order_id


async def attach_initial_payment(order_id: str, payment_id: str | None) -> None:
    if not payment_id:
        return
    async with async_session() as session:
        async with session.begin():
            row = await session.get(BillingPayment, order_id)
            if row and row.payment_id is None:
                row.payment_id = payment_id


async def get_initial_order(order_id: str) -> dict[str, Any] | None:
    async with async_session() as session:
        row = await session.get(BillingPayment, order_id)
        if not row:
            return None
        return {
            "order_id": row.order_id,
            "payment_id": row.payment_id,
            "user_id": row.user_id,
            "amount": row.amount,
            "purpose": row.purpose,
            "status": row.status,
        }


async def get_pending_initial_order(user_id: int) -> dict[str, Any] | None:
    async with async_session() as session:
        row = await session.scalar(
            select(BillingPayment).where(
                BillingPayment.user_id == user_id,
                BillingPayment.purpose == "initial",
                BillingPayment.status == "pending",
            ).order_by(BillingPayment.created_at.desc()).limit(1)
        )
        if not row:
            return None
        return {
            "order_id": row.order_id,
            "payment_id": row.payment_id,
            "user_id": row.user_id,
            "amount": row.amount,
            "purpose": row.purpose,
            "status": row.status,
        }


async def complete_initial_payment(order_id: str, payment_id: str) -> bool:
    """Atomically mark the 17 RUB payment paid and grant the first 3 days once."""
    now = datetime.now()
    async with sqlite_write_lock:
        async with async_session() as session:
            async with session.begin():
                order = await session.get(BillingPayment, order_id)
                if not order or order.purpose != "initial":
                    return False
                if order.payment_id and order.payment_id != payment_id:
                    return False
                if order.status == "paid":
                    return False
                order.payment_id = payment_id
                order.status = "paid"

                subscription = await session.get(Subscription, order.user_id)
                if subscription and subscription.plan == "forever" and subscription.is_active:
                    return True
                expiry = subscription.expiry_date if subscription else None
                start = expiry if expiry and expiry > now else now
                if subscription:
                    subscription.is_active = True
                    subscription.plan = "recurring_3day"
                    subscription.start_date = now
                    subscription.expiry_date = start + timedelta(days=ACCESS_DAYS)
                else:
                    session.add(Subscription(
                        user_id=order.user_id,
                        is_active=True,
                        plan="recurring_3day",
                        start_date=now,
                        expiry_date=start + timedelta(days=ACCESS_DAYS),
                    ))
    return True


async def get_or_create_recurring_key(user_id: int, initial_order_id: str) -> tuple[str, dict[str, Any] | None]:
    """Return a stable idempotency key and any previously created provider subscription."""
    key = f"vip3d-{initial_order_id}"[:128]
    async with sqlite_write_lock:
        async with async_session() as session:
            async with session.begin():
                row = await session.get(RecurringBilling, user_id)
                if row and row.subscription_id:
                    return row.idempotency_key or key, {
                        "subscription_id": row.subscription_id,
                        "state": row.state,
                        "billing_status": row.billing_status,
                        "pay_url": row.pay_url,
                    }
                if row:
                    row.initial_order_id = initial_order_id
                    row.idempotency_key = row.idempotency_key or key
                else:
                    session.add(RecurringBilling(
                        user_id=user_id,
                        initial_order_id=initial_order_id,
                        idempotency_key=key,
                        state="new",
                        billing_status="not_created",
                    ))
    return key, None


async def save_recurring_subscription(
    user_id: int, subscription_id: str, state: str, billing_status: str,
    pay_url: str | None,
) -> None:
    async with async_session() as session:
        async with session.begin():
            row = await session.get(RecurringBilling, user_id)
            if not row:
                raise ValueError("Recurring billing row was not initialized")
            row.subscription_id = subscription_id
            row.state = state
            row.billing_status = billing_status
            row.pay_url = pay_url
            row.updated_at = datetime.now()


async def get_recurring_billing(user_id: int) -> dict[str, Any] | None:
    async with async_session() as session:
        row = await session.get(RecurringBilling, user_id)
        if not row:
            return None
        return {
            "user_id": row.user_id,
            "initial_order_id": row.initial_order_id,
            "subscription_id": row.subscription_id,
            "state": row.state,
            "billing_status": row.billing_status,
            "pay_url": row.pay_url,
            "idempotency_key": row.idempotency_key,
        }


async def get_user_for_provider_subscription(subscription_id: str) -> int | None:
    async with async_session() as session:
        row = await session.scalar(
            select(RecurringBilling).where(
                RecurringBilling.subscription_id == subscription_id
            )
        )
        return row.user_id if row else None


async def update_recurring_state(user_id: int, state: str, billing_status: str) -> None:
    async with async_session() as session:
        async with session.begin():
            row = await session.get(RecurringBilling, user_id)
            if row:
                row.state = state
                row.billing_status = billing_status
                row.updated_at = datetime.now()


async def apply_recurring_charge(payment_id: str, user_id: int, amount: float) -> bool:
    """Apply a confirmed recurring payment once, atomically with access extension."""
    now = datetime.now()
    async with sqlite_write_lock:
        async with async_session() as session:
            async with session.begin():
                insert_result = await session.execute(
                    sqlite_insert(ProcessedCharge)
                    .values(payment_id=payment_id, user_id=user_id, amount=amount)
                    .on_conflict_do_nothing(index_elements=["payment_id"])
                )
                if insert_result.rowcount != 1:
                    return False

                subscription = await session.get(Subscription, user_id)
                expiry = subscription.expiry_date if subscription else None
                start = expiry if expiry and expiry > now else now
                new_expiry = start + timedelta(days=ACCESS_DAYS)
                if subscription:
                    subscription.is_active = True
                    subscription.plan = "recurring_3day"
                    subscription.start_date = now
                    subscription.expiry_date = new_expiry
                else:
                    session.add(Subscription(
                        user_id=user_id,
                        is_active=True,
                        plan="recurring_3day",
                        start_date=now,
                        expiry_date=new_expiry,
                    ))
    return True
