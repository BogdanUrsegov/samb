import logging
from aiogram import Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.formatting import html_decoration

from bot.database.utils import (
    add_message_link,
    increment_received_count,
    increment_sent_count,
)
from bot.create_bot import event_logger


logger = logging.getLogger(__name__)


async def forward_message(
    message: Message,
    state: FSMContext,
    bot: Bot,
    notification_prefix: str,
    keyboard_factory: callable,
) -> None:
    """Универсальная отправка сообщения с кнопками."""
    sender = message.from_user
    if not sender:
        logger.warning("Message without 'from_user'")
        return

    # Проверка медиа-группы
    if message.media_group_id:
        data = await state.get_data()
        if data.get("last_media_group_id") != message.media_group_id:
            await state.update_data(last_media_group_id=message.media_group_id)
            await message.answer(
                "❌ <b>Медиа-группы не поддерживаются</b>\n\nОтправляйте файлы по одному."
            )
        return

    # Получаем данные из state
    data = await state.get_data()
    recip_id = data.get("recip_id")
    cancel_msg_id = data.get("mess_id")

    if not recip_id:
        logger.error(f"Missing recip_id in state for user {sender.id}")
        await message.answer("🤔 Ошибка! Не могу определить получателя.")
        await state.clear()
        return

    # Проверка длины текста
    if message.content_type == "text" and len(message.text) > 4000:
        await message.answer("❌ <b>Превышен лимит символов</b> (макс. 4000).")
        await state.clear()
        return

    # Собираем клавиатуру сразу (передаём sender.id для callback_data)
    keyboard = keyboard_factory(sender.id)

    try:
        sent_message = None

        # === Текст ===
        if message.content_type == "text":
            safe_text = html_decoration.quote(message.text)
            sent_message = await bot.send_message(
                chat_id=recip_id,
                text=f"{notification_prefix}\n\n{safe_text}",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )

        # === Медиа с caption ===
        elif message.content_type in {"photo", "video", "audio", "document", "voice"}:
            safe_caption = html_decoration.quote(message.caption or "")
            full_caption = f"{notification_prefix}\n\n{safe_caption}"
            if len(full_caption) > 1024:
                full_caption = full_caption[:1020] + "..."

            sent_message = await bot.copy_message(
                chat_id=recip_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
                caption=full_caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,  # ⚡️ сразу
            )

        # === Стикер / опрос / прочее ===
        else:
            sent_message = await bot.copy_message(
                chat_id=recip_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
            # Текстовое уведомление с кнопками
            await bot.send_message(
                chat_id=recip_id,
                text=notification_prefix,
                reply_to_message_id=sent_message.message_id,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )

        logger.info(f"Sent {message.content_type}: {sender.id} → {recip_id}")

        # === Логирование отправки сообщения ===
        recipient_chat = await bot.get_chat(recip_id)
        recipient_name = recipient_chat.first_name or "Неизвестно"
        recipient_username = recipient_chat.username
        
        await event_logger.log_message_sent(
            sender_id=sender.id,
            sender_username=sender.username,
            sender_name=sender.first_name or "Неизвестно",
            recipient_id=recip_id,
            recipient_name=recipient_name,
            recipient_username=recipient_username,
            original_message=message,
            message_type=message.content_type,
        )

        # Сохраняем связь в БД
        await add_message_link(
            recipient_id=recip_id,
            received_message_id=sent_message.message_id,
            sender_id=sender.id,
            sender_message_id=message.message_id,
            sender_first_name=sender.first_name,
            sender_username=sender.username,
        )

        # Статистика
        await increment_received_count(recip_id)
        await increment_sent_count(sender.id)

        # Удаляем кнопку отмены (инлайн, без приватной функции)
        if cancel_msg_id:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=message.chat.id,
                    message_id=cancel_msg_id,
                    reply_markup=None,
                )
            except TelegramBadRequest:
                pass  # Сообщение уже удалено

        # Подтверждение
        await message.answer(
            "<b>✅ Сообщение отправлено!</b>\n\n<i>Нажми /start чтобы получить свою ссылку!</i>"
        )

    except TelegramBadRequest as e:
        err = str(e)
        if "blocked" in err:
            text = "❌ Получатель заблокировал бота."
        elif "chat not found" in err:
            text = "❌ Чат с получателем не найден."
        elif "deactivated" in err:
            text = "❌ Аккаунт получателя удалён."
        else:
            text = "❌ Ошибка отправки. Попробуй позже."
        await message.answer(text)
        logger.error(f"Telegram error: {e}")

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        await message.answer("⚙️ Произошла ошибка. Попробуй позже.")

    finally:
        await state.clear()