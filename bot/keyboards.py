from uuid import uuid4
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import os

from bot.utils.payments import create_invoice

# Константы для callback_data (добавлено : для единообразия)
PRICE_WEEKLY_RUB = int(os.getenv("PRICE_WEEKLY_RUB", 50))
PRICE_MONTHLY_RUB = int(os.getenv("PRICE_MONTHLY_RUB", 100))
PRICE_FOREVER_RUB = int(os.getenv("PRICE_FOREVER_RUB", 200))

REPLY_TO_CALL = "reply_to:"
WHO_SENT_CALL = "who_sent:"
SEND_ANOTHER_CALL = "send_another:"
CANCEL_ACTION_CALL = "cancel_action"
SUB_WEEKLY_CALL = "sub:weekly:"
SUB_MONTHLY_CALL = "sub:monthly:"
SUB_FOREVER_CALL = "sub:forever:"
SUB_CLOSE_CALL = "sub:close:"
CHECK_PAYMENT_CALL = "check:"


def create_reveal_reply_keyboard(
    recip_id: int, show_reply: bool = True, show_who_sent: bool = True
) -> InlineKeyboardMarkup:
    """Клавиатура с кнопками 'Ответить' и 'Кто это?'."""
    buttons = []

    if show_reply:
        buttons.append([
            InlineKeyboardButton(
                text="🗣️ Ответить",
                callback_data=f"{REPLY_TO_CALL}{recip_id}"
            )
        ])

    if show_who_sent:
        buttons.append([
            InlineKeyboardButton(
                text="🔍 Кто это?",
                callback_data=f"{WHO_SENT_CALL}{recip_id}"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_send_another_keyboard(recip_id: int) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой 'Отправить еще'."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="✏️ Отправить еще",
                callback_data=f"{SEND_ANOTHER_CALL}{recip_id}"
            )]
        ]
    )


def create_cancel_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой отмены."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data=CANCEL_ACTION_CALL)]
        ]
    )

def create_share_keyboard(user_link: str) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с кнопкой поделиться ссылкой.

    Args:
        user_link: Ссылка пользователя для получения анонимных сообщений

    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопкой поделиться
    """
    share_url = f"https://t.me/share/url?url={user_link}"
    buttons = [[InlineKeyboardButton(text="📤 Поделиться ссылкой", url=share_url)]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_subscription_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора плана подписки."""
    plans = [
        ("🥉 Неделя", PRICE_WEEKLY_RUB, SUB_WEEKLY_CALL),
        ("🥈 Месяц", PRICE_MONTHLY_RUB, SUB_MONTHLY_CALL),
        ("🥇 Навсегда", PRICE_FOREVER_RUB, SUB_FOREVER_CALL),
    ]
    
    buttons = [
        [InlineKeyboardButton(
            text=f"{name} - {price} ₽",
            callback_data=callback
        )]
        for name, price, callback in plans
    ]
    
    buttons.append([
        InlineKeyboardButton(
            text="❌ Закрыть",
            callback_data=SUB_CLOSE_CALL
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_payment_keyboard(amount: float) -> InlineKeyboardMarkup:
    """Клавиатура оплаты через Lava."""
    order_id = str(uuid4())
    invoice = create_invoice(amount, order_id)
    
    if not invoice or not invoice.get("status_check"):
        return None
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=invoice["data"]["url"])],
        [InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"{CHECK_PAYMENT_CALL}{order_id}")],
    ])