import logging
import os
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

from .utils.payments import check_invoice_status
from bot.database.utils import (
    add_or_update_subscription,
    add_user_if_not_exists,
    db_error,
    get_subscription,
    get_user,
    increment_link_clicks,
)
from bot.states import AnonymousMessaging
from bot.utils.forward_message import forward_message
from bot.utils.send_main_mess import send_main_mess

from .keyboards import (
    CANCEL_ACTION_CALL,
    CHECK_PAYMENT_CALL,
    REPLY_TO_CALL,
    SEND_ANOTHER_CALL,
    WHO_SENT_CALL,
    create_cancel_keyboard,
    create_payment_keyboard,
    create_reveal_reply_keyboard,
    create_send_another_keyboard,
    create_subscription_keyboard,
)

logger = logging.getLogger(__name__)
router = Router()

# Конфигурация
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
PRICE_WEEKLY_RUB = int(os.getenv("PRICE_WEEKLY_RUB", 50))
PRICE_MONTHLY_RUB = int(os.getenv("PRICE_MONTHLY_RUB", 100))
PRICE_FOREVER_RUB = int(os.getenv("PRICE_FOREVER_RUB", 200))

# Словари для оптимизации повторяющихся данных
PLAN_PRICES = {"weekly": PRICE_WEEKLY_RUB, "monthly": PRICE_MONTHLY_RUB, "forever": PRICE_FOREVER_RUB}
PLAN_PERIODS = {"weekly": "НЕДЕЛЯ", "monthly": "МЕСЯЦ", "forever": "НАВСЕГДА"}
PLAN_PERIODS_GEN = {"weekly": "неделю", "monthly": "месяц", "forever": "навсегда"}

# Текст для анонимного сообщения (используется в двух местах)
ANON_MESSAGE_TEXT = (
    "<i>🤫 Отлично! Теперь можешь отправить свое анонимное послание\n\n"
    "📝 Поддерживаются:\n• Текст\n• Фото\n• Видео\n• Кружки\n• Голосовые\n\n"
    "🚀 Всё полетит анонимно!</i>"
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


@router.message(StateFilter(AnonymousMessaging.waiting_for_message))
async def handle_anonymous_message(message: Message, state: FSMContext, bot: Bot):
    await forward_message(
        message=message, state=state, bot=bot,
        notification_prefix="💬 <b>У тебя новое сообщение!</b>",
        keyboard_factory=create_reveal_reply_keyboard,
    )


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
    
    text = "<b>✏️ Введите ваш ответ</b>\n\nОтправьте сообщение, и я анонимно перешлю его пользователю"
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
            f"<b>👑 VIP открывает отправителей!</b>\n\n"
            f"🥉 Неделя: <b>{PRICE_WEEKLY_RUB} ₽</b>\n"
            f"🥈 Месяц: <b>{PRICE_MONTHLY_RUB} ₽</b>\n"
            f"🥇 Навсегда: <b>{PRICE_FOREVER_RUB} ₽</b>\n\n"
            "<i>Выберите план ниже</i>",
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
    """Обработчик выбора плана подписки."""
    parts = query.data.split(":")
    
    # Закрытие меню
    if len(parts) >= 2 and parts[1] == "close":
        try:
            await query.message.delete()
        except TelegramBadRequest:
            pass
        return await query.answer("Закрыто")
        
    plan = parts[1]
    if plan not in PLAN_PRICES:
        return await query.answer("❌ Неизвестный план", show_alert=True)
        
    price = PLAN_PRICES[plan]
    keyboard = create_payment_keyboard(price)
    if not keyboard:
        return await query.answer("❌ Ошибка создания платежа", show_alert=True)
        
    await query.message.edit_text(
        f"🏷️ <b>СЧЁТ НА {price} ₽</b>\n\n"
        f"🕔 <b>СРОК:</b> {PLAN_PERIODS[plan]}\n\n"
        "<i>Нажмите кнопку для оплаты</i>",
        reply_markup=keyboard,
    )
    await query.answer()


@router.callback_query(F.data.startswith(CHECK_PAYMENT_CALL))
async def handle_payment_check(query: CallbackQuery):
    """Обработчик проверки оплаты."""
    order_id = query.data.split(":", 1)[1]
    user = query.from_user
    
    try:
        status_data = check_invoice_status(order_id)
        if not status_data or not status_data.get("status_check"):
            return await query.answer("❌ Ошибка проверки", show_alert=True)
        
        status = status_data["data"]["status"]
        if status != "success":
            return await query.answer("⏳ Платёж не найден, попробуйте позже", show_alert=True)
        
        # Определяем план по сумме
        amount = status_data["data"]["amount"]
        plan = next((k for k, v in PLAN_PRICES.items() if v == amount), None)
        
        if not plan:
            return await query.answer("❌ Неизвестная сумма", show_alert=True)
            
        await add_or_update_subscription(user.id, plan)
        
        await query.message.edit_text(
            f"✅ <b>Оплата подтверждена!</b>\n\n"
            f"🎉 <b>VIP активен на {PLAN_PERIODS_GEN[plan]}!</b>",
            reply_markup=None,
        )
        await query.answer("✅ Оплачено!")
        await event_logger.log_subscription_purchase(
            user_id=user.id,
            username=user.username,
            first_name=user.full_name,
            plan=PLAN_PERIODS_GEN[plan],
            amount=amount
        )

        
    except Exception as e:
        logger.exception(f"Payment check error: {e}")
        await query.answer("⚙️ Ошибка проверки", show_alert=True)


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