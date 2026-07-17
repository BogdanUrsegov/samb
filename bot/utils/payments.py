"""
Платежи через RollyPay API.
"""

import os
import uuid
import requests

API_KEY = os.getenv("ROLLYPAY_API_KEY")
API_BASE_URL = "https://rollypay.io/api/v1"


def _send_request(
    method: str,
    endpoint: str,
    payload: dict | None = None,
) -> dict | None:
    """Отправляет запрос к RollyPay API."""

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
        "X-Nonce": str(uuid.uuid4()),
    }

    url = f"{API_BASE_URL}/{endpoint}"

    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=payload,
            timeout=10,
        )

        response.raise_for_status()
        return response.json()

    except Exception as e:
        print(f"RollyPay API error: {e}")
        return None


def create_invoice(
    amount: float,
    order_id: str,
    comment: str = None,
) -> dict | None:
    """Создаёт счёт на оплату."""

    payload = {
        "amount": f"{amount:.2f}",
        "payment_currency": "RUB",
        "order_id": order_id,
        "payment_method": "sbp",
    }

    if comment:
        payload["description"] = comment

    return _send_request(
        "POST",
        "payments",
        payload,
    )


def check_invoice_status(payment_id: str) -> dict | None:
    """Проверяет статус счёта."""

    return _send_request(
        "GET",
        f"payments/{payment_id}",
    )