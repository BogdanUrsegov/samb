import os
import logging
import asyncio
from uuid import uuid4
from aiogram.types import ErrorEvent
from aiogram.exceptions import TelegramBadRequest
from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.formatting import html_decoration

from bot.create_bot import event_logger
from bot.utils.create_link import create_link
from bot.utils.resolve_user_id import resolve_user_id
from bot.utils.show_advert import show_advert

from .utils.payments import (
    check_invoice_status,
    create_invoice,
    create_recurring_subscription,
    get_recurring_subscription,
    stop_recurring_subscription,
)
from bot.database.utils import (
    add_or_update_subscription,
    add_user_if_not_exists,
    db_error,
    get_subscription,
    get_user,
    increment_link_clicks,
)
from bot.database.billing import (
    apply_recurring_charge,
    attach_initial_payment,
    complete_initial_payment,
    create_initial_order,
    get_initial_order,
    get_or_create_recurring_key,
    get_pending_initial_order,
    get_recurring_billing,
    get_user_for_provider_subscription,
    save_recurring_subscription,
    update_recurring_state,
)
from bot.states import AnonymousMessaging
from bot.utils.forward_message import forward_message
from bot.utils.send_main_mess import send_main_mess

from .keyboards import (
    CANCEL_ACTION_CALL,
    CHECK_PAYMENT_CALL,
    RECURRING_CHECK_CALL,
    RECURRING_RETRY_CALL,
    RECURRING_STOP_CALL,
    START_INITIAL_CALL,
    REPLY_TO_CALL,
    SEND_ANOTHER_CALL,
    WHO_SENT_CALL,
    create_cancel_keyboard,
    create_payment_keyboard,
    create_recurring_consent_keyboard,
    create_reveal_reply_keyboard,
    create_send_another_keyboard,
    create_subscription_keyboard,
)

logger = logging.getLogger(__name__)
router = Router()

# Конфигурация
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
INITIAL_AMOUNT_RUB = 17
RECURRING_AMOUNT_RUB = 299
ACCESS_DAYS = 3

# Текст для анонимного сообщения (используется в двух местах)
ANON_MESSAGE_TEXT = (
    "🚀 Здесь можно отправить <b>анонимное сообщение</b> человеку, который опубликовал эту ссылку\n\n"
    "<i>📝 Поддерживаются:\n• Текст\n• Фото\n• Видео\n• Кружки\n• Голосовые\n\n"
    "🤫 Всё полетит анонимно!</i>"
)


# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================

async def _set_anonymous_state(callback: CallbackQuery, state: FSMContext, recip_id: int, text: str, state_name):
    """Хелпер для установки FSM состояния и отправки сообщения с клавиатурой отмены."""
    mess = await callback.message.answer(
        text, parse_mode=ParseMode.HTML, disable_web_page_preview=True,
        reply_markup=create_cancel_keyboard()
    )
    await state.set_state(state_name)
    await state.update_data(recip_id=recip_id, mess_id=mess.message_id)


# ==========================================
# ОБРАБОТЧИКИ КОМАНД И СТАРТОВЫХ ССЫЛОК
# ==========================================

@router.message(CommandStart(deep_link=True), StateFilter(None))
async def handle_start_deep_link(message: Message, state: FSMContext, bot: Bot):
    """Обработчик /start с параметром (deep link)."""
    user = message.from_user
    res = await add_user_if_not_exists(user.id, user.first_name or "Пользователь", user.username, user.last_name)
    if res:
        await event_logger.log_new_user(
            user_id=user.id,
            username=user.username,
            first_name=user.full_name
        )
    if not message.text or len(message.text.split()) < 2:
        logger.warning(f"Deep link payload missing. User: {user.id}")
        return await message.answer("😕 Не удалось распознать ссылку. Попробуйте еще раз.")
    
    payload = message.text.split(" ", 1)[1]
    logger.debug(f"Extracted payload: '{payload}' for user {user.id}")

    recip_id = await resolve_user_id(payload)

    # 4. Финальная проверка (если ID равен 0 или None)
    if not recip_id:
        return await message.answer("🔗 <i>Упс! Эта ссылка недействительна. Попроси у пользователя свежую.</i>")
    
    if recip_id == user.id:
        logger.info(f"User {user.id} tried to send message to themselves.")
        return await message.answer(
            "🤔 <i>Нельзя отправлять сообщения самому себе! Попробуйте отправить кому-то другому.</i>",
            disable_web_page_preview=True
        )

    try:
        await state.set_state(AnonymousMessaging.waiting_for_message)
        mess = await message.answer(
            ANON_MESSAGE_TEXT, parse_mode=ParseMode.HTML, disable_web_page_preview=True,
            reply_markup=create_cancel_keyboard()
        )
        await state.update_data(recip_id=recip_id, mess_id=mess.message_id)
        await increment_link_clicks(recip_id)
        await event_logger.log_link_click(
            user_id=user.id,
            link_owner_id=recip_id,
            custom_param=payload
        )
        logger.info(f"User {user.id} state set to Sending.wait for recipient {recip_id}")
    except Exception as e:
        logger.exception(f"Error setting state for user {user.id}: {e}")
        await state.clear()


@router.message(CommandStart(deep_link=False), StateFilter(None))
async def handle_start_regular(message: Message, bot: Bot):
    """Обработчик /start без параметров."""
    user = message.from_user
    res = await add_user_if_not_exists(user.id, user.first_name or "Пользователь", user.username, user.last_name)
    if res:
        await event_logger.log_new_user(
            user_id=user.id,
            username=user.username,
            first_name=user.full_name
        )
    await send_main_mess(
        send_func=message.answer,
        bot_username=(await bot.me()).username,
        user_id=user.id
    )


@router.message(Command("profile"))
async def cmd_profile(message: Message, bot: Bot):
    """Обработчик команды /profile."""
    user_id = message.from_user.id
    try:
        user = await get_user(user_id)
        if not user:
            return await message.answer("Не удалось загрузить ваш профиль. Попробуйте /start и затем снова /profile.")
        
        bot_username = (await bot.me()).username
        link = await create_link(user_id, bot_username)
        text = (
            "👤 <b>Ваш профиль</b>\n\n"
            f"📬 Получено сообщений: {user['messages_received']}\n"
            f"✉️ Отправлено сообщений: {user['messages_sent']}\n"
            f"🔗 Переходов по вашей ссылке: {user['link_clicks']}\n\n"
            "🔗 <b>Ваша текущая ссылка:</b>\n"
            f"{link}"
        )
        await message.answer(text, disable_web_page_preview=True, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Ошибка при получении профиля пользователя {user_id}: {e}")
        await message.answer(
            "⚠️ <i>Произошла ошибка при загрузке вашего профиля. Пожалуйста, попробуйте позже</i>",
            parse_mode=ParseMode.HTML, disable_web_page_preview=True
        )


# ==========================================
# ОБРАБОТЧИКИ СООБЩЕНИЙ (FSM)
# ==========================================

@router.message(StateFilter(AnonymousMessaging.waiting_for_reply))
async def handle_responding_message(message: Message, state: FSMContext, bot: Bot):
    await forward_message(
        message=message, state=state, bot=bot,
        notification_prefix="💬 <b>Ответ на ваше сообщение:</b>",
        keyboard_factory=create_send_another_keyboard,
    )
    await show_advert(message.from_user.id)


@router.message(StateFilter(AnonymousMessaging.waiting_for_message))
async def handle_anonymous_message(message: Message, state: FSMContext, bot: Bot):
    await forward_message(
        message=message, state=state, bot=bot,
        notification_prefix="💬 <b>У тебя новое сообщение!</b>",
        keyboard_factory=create_reveal_reply_keyboard,
    )
    await show_advert(message.from_user.id)



# ==========================================
# CALLBACK ОБРАБОТЧИКИ (ДЕЙСТВИЯ)
# ==========================================

@router.callback_query(F.data.startswith(SEND_ANOTHER_CALL))
async def handle_action_add_mess(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обработчик кнопки 'Новое сообщение'."""
    await callback.answer("Новое сообщение...")
    try:
        recip_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        return await callback.message.answer("❌ Ошибка: не удалось определить получателя.")
    
    await _set_anonymous_state(callback, state, recip_id, ANON_MESSAGE_TEXT, AnonymousMessaging.waiting_for_message)


@router.callback_query(F.data.startswith(REPLY_TO_CALL))
async def handle_action_reply(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обработчик кнопки 'Ответить'."""
    await callback.answer("Ответ на сообщение...")
    try:
        recip_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        return await callback.message.answer("❌ Ошибка: не удалось определить получателя.")
    
    text = "<b>✏️ Введите ваш ответ</b>\n\nОтправьте сообщение и я анонимно перешлю его пользователю"
    logger.info(f"User {callback.from_user.id} is replying to user {recip_id}")
    await _set_anonymous_state(callback, state, recip_id, text, AnonymousMessaging.waiting_for_reply)


@router.callback_query(F.data == CANCEL_ACTION_CALL)
async def handle_action_cancel(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обработчик кнопки 'Отмена'."""
    await callback.answer("Отмена действия...")
    await send_main_mess(
        send_func=callback.message.edit_text,
        bot_username=(await bot.me()).username,
        user_id=callback.from_user.id
    )
    await state.clear()


# ==========================================
# CALLBACK ОБРАБОТЧИКИ (VIP И ОПЛАТА)
# ==========================================

@router.callback_query(F.data.startswith(WHO_SENT_CALL))
async def handle_reveal_callback(query: CallbackQuery, bot: Bot):
    """Обработчик кнопки 'Кто это?'."""
    try:
        sender_id = int(query.data.split(":")[1])
    except (IndexError, ValueError):
        return await query.answer("😕 Неверный формат данных", show_alert=True)

    user_id = query.from_user.id
    subscription = await get_subscription(user_id)
    
    # Если нет активной VIP-подписки
    if not (subscription and subscription.get("is_active")):
        keyboard = create_subscription_keyboard()
        await query.message.reply(
            "<b>👑 Откройте отправителей с VIP</b>\n\n"
            "🎁 Первые 3 дня — <b>17 ₽</b> разовым платежом.\n"
            "🔁 Затем можно отдельно согласиться на автопродление: "
            "<b>299 ₽ каждые 3 дня</b> через СБП.\n\n"
            "Автопродление не включается без вашего подтверждения в банковском приложении. "
            "Отключить его можно в любой момент.",
            reply_markup=keyboard,
        )
        return await query.answer()
    
    
    if not sender_id:
        return await query.answer("😕 Не удалось найти отправителя", show_alert=True)
    
    chat = await bot.get_chat(sender_id)
    name = html_decoration.quote(chat.full_name)
    username = f"@{chat.username}" if chat.username else "отсутствует"
    
    await query.message.reply(
        f"🕵️‍♂️ <b>Отправитель</b>\n\n"
        f"👤 <b>Имя:</b> {name}\n"
        f"🔗 <b>Username:</b> {username}"
    )
    await query.answer()


@router.callback_query(F.data.startswith("sub:"))
async def handle_subscription_choice(query: CallbackQuery):
    """Start the one-time 17 RUB, 3-day VIP offer."""
    parts = query.data.split(":", 1)
    if len(parts) == 2 and parts[1] == "close":
        try:
            await query.message.delete()
        except TelegramBadRequest:
            pass
        return await query.answer("Закрыто")
    if query.data != START_INITIAL_CALL:
        return await query.answer("❌ Неизвестный вариант", show_alert=True)

    user_id = query.from_user.id
    order_id = await create_initial_order(user_id, str(uuid4()))
    invoice = await asyncio.to_thread(
        create_invoice, INITIAL_AMOUNT_RUB, order_id, "VIP на 3 дня"
    )
    if not invoice or not invoice.get("pay_url"):
        return await query.answer(
            "❌ Не удалось создать платёж. Попробуйте ещё раз позже.",
            show_alert=True,
        )

    payment_id = invoice.get("payment_id") or invoice.get("id")
    if payment_id:
        await attach_initial_payment(order_id, str(payment_id))

    await query.message.edit_text(
        "💳 <b>VIP на 3 дня — 17 ₽</b>\n\n"
        "Это разовый платёж. После его подтверждения VIP будет активен 3 дня. "
        "Затем вы сможете отдельно подключить автопродление за 299 ₽ каждые 3 дня. "
        "Списание 299 ₽ не начнётся без подтверждения в банке.",
        reply_markup=create_payment_keyboard(
            invoice["pay_url"], str(payment_id or ""), order_id
        ),
    )
    await query.answer()


async def _prepare_recurring_consent(user_id: int, initial_order_id: str):
    """Create or recover the same provider subscription using a stable idempotency key."""
    key, existing = await get_or_create_recurring_key(user_id, initial_order_id)
    if existing and existing.get("subscription_id"):
        return existing

    response = await asyncio.to_thread(create_recurring_subscription, user_id, key)
    if not response:
        return None
    subscription_id = response.get("id") or response.get("subscription_id")
    if not subscription_id:
        logger.error("RollyPay recurring create response had no subscription id")
        return None
    pay_url = response.get("pay_url") or response.get("redirect_url")
    state = str(response.get("state") or "new")
    billing_status = str(response.get("billing_status") or "consent_pending")
    await save_recurring_subscription(
        user_id, str(subscription_id), state, billing_status, pay_url
    )
    return {
        "subscription_id": str(subscription_id),
        "state": state,
        "billing_status": billing_status,
        "pay_url": pay_url,
    }


@router.callback_query(F.data.startswith(CHECK_PAYMENT_CALL))
async def handle_payment_check(query: CallbackQuery):
    """Verify the 17 RUB payment against RollyPay and grant access once."""
    order_id = query.data.split(":", 1)[1]
    user = query.from_user
    order = await get_initial_order(order_id)
    if not order or order["user_id"] != user.id or order["purpose"] != "initial":
        return await query.answer("❌ Платёж не найден", show_alert=True)

    if order["status"] != "paid":
        payment_id = order.get("payment_id")
        if not payment_id:
            return await query.answer(
                "⏳ Счёт ещё создаётся. Попробуйте чуть позже.",
                show_alert=True,
            )
        payment = await asyncio.to_thread(check_invoice_status, payment_id)
        if not payment:
            return await query.answer("❌ Не удалось проверить платёж", show_alert=True)
        if payment.get("status") != "paid":
            return await query.answer("⏳ Платёж ещё не оплачен", show_alert=True)

        try:
            amount = round(float(payment.get("amount", 0)), 2)
        except (TypeError, ValueError):
            amount = 0
        currency = str(payment.get("currency") or payment.get("payment_currency") or "RUB")
        provider_order_id = payment.get("order_id")
        provider_payment_id = str(payment.get("payment_id") or payment.get("id") or payment_id)
        if amount != INITIAL_AMOUNT_RUB or currency != "RUB" or (
            provider_order_id and provider_order_id != order_id
        ):
            logger.error("RollyPay initial payment mismatch for order %s", order_id)
            return await query.answer(
                "❌ Сумма или данные платежа не совпали. Обратитесь в поддержку.",
                show_alert=True,
            )
        await complete_initial_payment(order_id, provider_payment_id)
        order = await get_initial_order(order_id)

    recurring = await _prepare_recurring_consent(user.id, order_id)
    if recurring is None:
        await query.message.edit_text(
            "✅ <b>Оплата 17 ₽ подтверждена!</b> VIP активен 3 дня.\n\n"
            "Не удалось подготовить ссылку на автопродление. Никаких следующих списаний "
            "не будет, пока вы не подтвердите привязку. Попробуйте повторить позже.",
            reply_markup=create_recurring_consent_keyboard(None, has_subscription=False),
        )
        return await query.answer("Оплачено; автопродление пока не подключено")

    await query.message.edit_text(
        "✅ <b>Оплата 17 ₽ подтверждена!</b>\n"
        "🎁 VIP активен 3 дня.\n\n"
        "По желанию подключите автопродление: <b>299 ₽ каждые 3 дня</b>. "
        "Перейдите по ссылке и подтвердите условия в банковском приложении. "
        "До подтверждения привязки регулярных списаний не будет.",
        reply_markup=create_recurring_consent_keyboard(
            recurring.get("pay_url"),
            has_subscription=bool(recurring.get("subscription_id")),
        ),
    )
    await query.answer("✅ Оплата подтверждена")


@router.callback_query(F.data == RECURRING_RETRY_CALL)
async def handle_recurring_retry(query: CallbackQuery):
    order = await get_pending_initial_order(query.from_user.id)
    if not order:
        # A completed initial order is retained for recurring setup.
        billing = await get_recurring_billing(query.from_user.id)
        if billing:
            order_id = billing["initial_order_id"]
        else:
            return await query.answer(
                "Сначала оплатите VIP на 3 дня за 17 ₽.",
                show_alert=True,
            )
    else:
        order_id = order["order_id"]

    recurring = await _prepare_recurring_consent(query.from_user.id, order_id)
    if not recurring:
        return await query.answer(
            "Не удалось создать ссылку. Проверьте настройки RollyPay и попробуйте позже.",
            show_alert=True,
        )
    await query.message.edit_reply_markup(
        reply_markup=create_recurring_consent_keyboard(
            recurring.get("pay_url"), has_subscription=True
        )
    )
    await query.answer("Ссылка на привязку готова")


@router.callback_query(F.data == RECURRING_CHECK_CALL)
async def handle_recurring_check(query: CallbackQuery):
    billing = await get_recurring_billing(query.from_user.id)
    if not billing or not billing.get("subscription_id"):
        return await query.answer("Привязка ещё не создана", show_alert=True)

    provider = await asyncio.to_thread(
        get_recurring_subscription, billing["subscription_id"]
    )
    if not provider:
        return await query.answer("Не удалось проверить привязку", show_alert=True)

    state = str(provider.get("state") or "new")
    billing_status = str(provider.get("billing_status") or "review")
    await update_recurring_state(query.from_user.id, state, billing_status)

    if state == "active" and billing_status == "enabled":
        await query.message.edit_reply_markup(
            reply_markup=create_recurring_consent_keyboard(
                billing.get("pay_url"), has_subscription=True
            )
        )
        return await query.answer(
            "✅ Автопродление подключено. Доступ продлевается после успешных списаний.",
            show_alert=True,
        )
    if billing_status == "stopped" or state == "stop":
        return await query.answer("Автопродление отключено", show_alert=True)
    if billing_status == "review":
        return await query.answer(
            "RollyPay проверяет привязку. Не создавайте новую подписку; обратитесь в поддержку.",
            show_alert=True,
        )
    await query.answer(
        f"Статус привязки: {billing_status}. Подтвердите её в банковском приложении.",
        show_alert=True,
    )


@router.callback_query(F.data == RECURRING_STOP_CALL)
async def handle_recurring_stop(query: CallbackQuery):
    billing = await get_recurring_billing(query.from_user.id)
    if not billing or not billing.get("subscription_id"):
        return await query.answer("Автопродление не подключено", show_alert=True)

    result = await asyncio.to_thread(
        stop_recurring_subscription, billing["subscription_id"]
    )
    if not result:
        return await query.answer(
            "Не удалось подтвердить отключение. Попробуйте позже.",
            show_alert=True,
        )
    provider = await asyncio.to_thread(
        get_recurring_subscription, billing["subscription_id"]
    )
    if not provider:
        return await query.answer(
            "Запрос отправлен, но статус не подтверждён. Проверьте позже.",
            show_alert=True,
        )
    state = str(provider.get("state") or "new")
    billing_status = str(provider.get("billing_status") or "review")
    await update_recurring_state(query.from_user.id, state, billing_status)
    if state != "stop" or billing_status != "stopped":
        return await query.answer(
            "RollyPay ещё не подтвердил отключение. Текущий доступ сохраняется.",
            show_alert=True,
        )
    await query.answer(
        "Автопродление отключено. Уже оплаченный срок VIP сохраняется.",
        show_alert=True,
    )

@router.callback_query(F.data == "cancel_payment")
async def handle_cancel_payment(query: CallbackQuery):
    """Обработчик отмены платежа."""
    await query.message.edit_text(
        "❌ <b>Платёж отменён</b>\n\n"
        "<i>Вы можете попробовать снова, нажав <b>Кто это?</b></i>"
    )
    await query.answer("Отменено")

@router.message(Command("policy"))
async def handle_policy_command(message: Message, bot: Bot):
    await message.answer(
        '<a href="https://telegra.ph/POLITIKA-KONFIDENCIALNOSTI-09-30-71">политика конфиденциальности</a>, <a href="https://telegra.ph/PUBLICHNAYA-OFERTA-09-30-5">публичная оферта</a>, <a href="https://telegra.ph/POLITIKA-VOZVRATOV-09-30">политика возвратов</a>',
        parse_mode="HTML",
        disable_web_page_preview=True,
    )

# ==========================================
# FALLBACK ОБРАБОТЧИК
# ==========================================

@router.message(Command("test"))
async def test_error(message: Message):
    """Тестовая команда для проверки логирования."""
    raise ValueError("Test error for logging")

@router.message(Command("test_db"))
async def test_db(message: Message):
    await db_error()

@router.message()
async def handle_ignore(message: Message, bot: Bot):
    """Fallback обработчик для всех остальных сообщений."""
    await send_main_mess(
        send_func=message.answer,
        bot_username=(await bot.me()).username,
        user_id=message.from_user.id
    )

@router.errors()
async def errors_handler(event: ErrorEvent):
    """Обработчик всех ошибок."""
    context = f"Update: {event.update.update_id}"
    await event_logger.log_error(event.exception, context)
    return False  # False = ошибка не обработана, пробрасывается дальше