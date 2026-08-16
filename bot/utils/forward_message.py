import logging
from collections.abc import Callable

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.formatting import html_decoration

from bot.create_bot import event_logger
from bot.database.utils import add_message_link, increment_received_count, increment_sent_count

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 4000
MAX_CAPTION_LENGTH = 1024
SUPPORTED_MEDIA_TYPES = {"photo", "video", "audio", "document", "voice"}


async def forward_message(
    message: Message,
    state: FSMContext,
    bot: Bot,
    notification_prefix: str,
    keyboard_factory: Callable[[int], object],
) -> None:
    """Forward an anonymous message, persist its mapping and update counters."""
    sender = message.from_user
    if sender is None:
        logger.warning("Message without from_user")
        return

    if message.media_group_id:
        data = await state.get_data()
        if data.get("last_media_group_id") != message.media_group_id:
            await state.update_data(last_media_group_id=message.media_group_id)
            await message.answer(
                "❌ <b>Медиа-группы не поддерживаются</b>\n\nОтправляйте файлы по одному."
            )
        return

    data = await state.get_data()
    recipient_id = data.get("recip_id")
    cancel_message_id = data.get("mess_id")

    if not recipient_id:
        logger.error("Missing recip_id in state for user %s", sender.id)
        await message.answer("🤔 Ошибка! Не могу определить получателя.")
        await state.clear()
        return

    if message.content_type == "text" and len(message.text or "") > MAX_TEXT_LENGTH:
        await message.answer("❌ <b>Превышен лимит символов</b> (макс. 4000).")
        await state.clear()
        return

    keyboard = keyboard_factory(sender.id)

    try:
        # Fetch recipient metadata before sending. This prevents a successful
        # Telegram send from being reported as a generic error if logging fails later.
        recipient_chat = await bot.get_chat(recipient_id)
        recipient_name = recipient_chat.first_name or "Неизвестно"
        recipient_username = recipient_chat.username

        if message.content_type == "text":
            safe_text = html_decoration.quote(message.text or "")
            sent_message = await bot.send_message(
                chat_id=recipient_id,
                text=f"{notification_prefix}\n\n{safe_text}",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        elif message.content_type in SUPPORTED_MEDIA_TYPES:
            safe_caption = html_decoration.quote(message.caption or "")
            full_caption = f"{notification_prefix}\n\n{safe_caption}"
            if len(full_caption) > MAX_CAPTION_LENGTH:
                full_caption = full_caption[: MAX_CAPTION_LENGTH - 3] + "..."

            sent_message = await bot.copy_message(
                chat_id=recipient_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
                caption=full_caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        else:
            sent_message = await bot.copy_message(
                chat_id=recipient_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
            await bot.send_message(
                chat_id=recipient_id,
                text=notification_prefix,
                reply_to_message_id=sent_message.message_id,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )

        logger.info("Sent %s: %s -> %s", message.content_type, sender.id, recipient_id)

        await event_logger.log_message_sent(
            sender_id=sender.id,
            sender_username=sender.username,
            sender_name=sender.first_name or "Неизвестно",
            recipient_id=recipient_id,
            recipient_name=recipient_name,
            recipient_username=recipient_username,
            original_message=message,
            message_type=message.content_type,
        )

        await add_message_link(
            recipient_id=recipient_id,
            received_message_id=sent_message.message_id,
            sender_id=sender.id,
            sender_message_id=message.message_id,
            sender_first_name=sender.first_name,
            sender_username=sender.username,
        )
        await increment_received_count(recipient_id)
        await increment_sent_count(sender.id)

        if cancel_message_id:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=message.chat.id,
                    message_id=cancel_message_id,
                    reply_markup=None,
                )
            except TelegramBadRequest:
                logger.debug("Could not clear cancel keyboard", exc_info=True)

        await message.answer(
            "<b>✅ Сообщение отправлено!</b>\n\n<i>Нажми /start чтобы получить свою ссылку!</i>"
        )

    except TelegramBadRequest as exc:
        error = str(exc).lower()
        if "blocked" in error:
            text = "❌ Получатель заблокировал бота."
        elif "chat not found" in error:
            text = "❌ Чат с получателем не найден."
        elif "deactivated" in error:
            text = "❌ Аккаунт получателя удалён."
        else:
            text = "❌ Ошибка отправки. Попробуй позже."
        await message.answer(text)
        logger.error("Telegram error while forwarding message: %s", exc)
    except Exception:
        logger.exception("Unexpected error while forwarding message")
        await message.answer("⚙️ Произошла ошибка. Попробуй позже.")
    finally:
        await state.clear()
