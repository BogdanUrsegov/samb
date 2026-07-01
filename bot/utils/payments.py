"""
Платежи через Lava.ru API.
"""

import os
import requests
import json
import hmac
import hashlib

SHOP_ID = os.getenv("lava_shop_id")
SECRET_KEY = os.getenv("SECRET_KEY")
API_BASE_URL = "https://api.lava.ru/business"


def _send_request(endpoint: str, payload: dict) -> dict | None:
    """Отправляет подписанный запрос к Lava API."""
    url = f"{API_BASE_URL}/{endpoint}"
    sorted_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    signature = hmac.new(
        SECRET_KEY.encode(), sorted_payload.encode(), hashlib.sha256
    ).hexdigest()
    
    payload["signature"] = signature
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Lava API error: {e}")
        return None


def create_invoice(amount: float, order_id: str, comment: str = None) -> dict | None:
    """Создаёт счёт на оплату."""
    payload = {"shopId": SHOP_ID, "sum": amount, "orderId": order_id}
    if comment:
        payload["comment"] = comment
    return _send_request("invoice/create", payload)


def check_invoice_status(order_id: str) -> dict | None:
    """Проверяет статус счёта."""
    return _send_request("invoice/status", {"shopId": SHOP_ID, "orderId": order_id})