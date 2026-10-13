from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

INITIAL_AMOUNT_RUB = 17

REPLY_TO_CALL = "reply_to:"
WHO_SENT_CALL = "who_sent:"
SEND_ANOTHER_CALL = "send_another:"
CANCEL_ACTION_CALL = "cancel_action"
CHECK_PAYMENT_CALL = "check:"
START_INITIAL_CALL = "sub:initial"
SUB_CLOSE_CALL = "sub:close"
RECURRING_RETRY_CALL = "recurring_retry"
RECURRING_CHECK_CALL = "recurring_check"
RECURRING_STOP_CALL = "recurring_stop"


def create_reveal_reply_keyboard(
    recip_id: int, show_reply: bool = True, show_who_sent: bool = True
) -> InlineKeyboardMarkup:
    buttons = []
    if show_reply:
        buttons.append([InlineKeyboardButton(
            text="🗣️ Ответить", callback_data=f"{REPLY_TO_CALL}{recip_id}"
        )])
    if show_who_sent:
        buttons.append([InlineKeyboardButton(
            text="👁 Кто это?", callback_data=f"{WHO_SENT_CALL}{recip_id}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_send_another_keyboard(recip_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✍️ Отправить еще", callback_data=f"{SEND_ANOTHER_CALL}{recip_id}"
        )
    ]])


def create_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Отменить", callback_data=CANCEL_ACTION_CALL)
    ]])


def create_share_keyboard(user_link: str) -> InlineKeyboardMarkup:
    share_url = f"https://t.me/share/url?url={user_link}"
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📤 Поделиться ссылкой", url=share_url)
    ]])


def create_subscription_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="👑 VIP на 3 дня — 17 ₽", callback_data=START_INITIAL_CALL
        )],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data=SUB_CLOSE_CALL)],
    ])


def create_payment_keyboard(
    pay_url: str, payment_id: str, order_id: str
) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="💳 Оплатить 17 ₽", url=pay_url)]]
    buttons.append([InlineKeyboardButton(
        text="✅ Проверить оплату", callback_data=f"{CHECK_PAYMENT_CALL}{order_id}"
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_recurring_consent_keyboard(
    pay_url: str | None,
    has_subscription: bool = False,
) -> InlineKeyboardMarkup:
    buttons = []
    if pay_url:
        buttons.append([InlineKeyboardButton(
            text="🔁 Подключить автопродление · 299 ₽ / 3 дня", url=pay_url
        )])
    buttons.append([InlineKeyboardButton(
        text="🔎 Проверить привязку", callback_data=RECURRING_CHECK_CALL
    )])
    if has_subscription:
        buttons.append([InlineKeyboardButton(
            text="🛑 Отключить автопродление", callback_data=RECURRING_STOP_CALL
        )])
    else:
        buttons.append([InlineKeyboardButton(
            text="🔄 Повторить создание ссылки", callback_data=RECURRING_RETRY_CALL
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
