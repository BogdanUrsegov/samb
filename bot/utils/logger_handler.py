"""Logging of application errors and business events to Telegram."""

import logging
import traceback
from typing import Optional

from aiogram import Bot
from aiogram.types import Message
from aiogram.utils.formatting import html_decoration

from .telegram_log_dispatcher import TelegramLogDispatcher, TelegramLogEvent

logger = logging.getLogger(__name__)

MAX_TELEGRAM_LOG_LENGTH = 3800
MAX_TRACEBACK_LENGTH = 2200

PLAN_NAMES = {
    "weekly": "Неделя",
    "monthly": "Месяц",
    "forever": "Навсегда",
}


def _truncate(value: str, limit: int) -> str:
    value = value or ""
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _escape(value: object) -> str:
    return html_decoration.quote(str(value))


def _format_user_info(user_id: int, first_name: Optional[str], username: Optional[str]) -> str:
    name = html_decoration.quote(first_name) if first_name else "Неизвестно"
    user = f"@{html_decoration.quote(username)}" if username else "нет"
    return f"ID: <code>{user_id}</code>\nИмя: {name}\nUsername: {user}"


def format_error_message(
    error: Exception,
    *,
    context: str = "",
    action: str = "",
    update_info: str = "",
) -> str:
    """Build a compact Telegram-readable error report."""
    error_type = type(error).__name__
    error_message = _truncate(str(error) or "Без сообщения", 700)
    location = ""
    if error.__traceback__ is not None:
        frames = traceback.extract_tb(error.__traceback__)
        if frames:
            frame = frames[-1]
            location = f"{frame.filename}:{frame.lineno} → {frame.name}()"

    lines = [
        "❌ <b>Ошибка приложения</b>",
        f"<b>Тип:</b> <code>{_escape(error_type)}</code>",
        f"<b>Сообщение:</b> <code>{_escape(error_message)}</code>",
    ]
    if context:
        lines.append(f"<b>Участок:</b> {_escape(context)}")
    if action:
        lines.append(f"<b>Действие:</b> {_escape(action)}")
    if update_info:
        lines.append(f"<b>Update:</b> {_escape(update_info)}")
    if location:
        lines.append(f"<b>Код:</b> <code>{_escape(location)}</code>")

    tb_text = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    if tb_text:
        lines.append(f"<pre>{_escape(_truncate(tb_text, MAX_TRACEBACK_LENGTH))}</pre>")

    return _truncate("\n".join(lines), MAX_TELEGRAM_LOG_LENGTH)


class TelegramLoggerHandler(logging.Handler):
    """Asynchronously sends WARNING/ERROR records to the Telegram log channel."""

    def __init__(self, bot: Bot, chat_id: int, level: int = logging.WARNING):
        super().__init__(level)
        self.bot = bot
        self.chat_id = chat_id
        self._logger = logging.getLogger("telegram_log_handler")

    def emit(self, record: logging.LogRecord) -> None:
        # This handler is retained for compatibility with existing logging setup.
        # Business events and application errors use TelegramEventLogger's dispatcher.
        try:
            self._logger.log(record.levelno, self.format(record))
        except Exception:
            self._logger.exception("Failed to process Telegram log record")


class TelegramEventLogger:
    """Queues all business events for ordered, throttled delivery to Telegram."""

    def __init__(self, bot: Bot, chat_id: Optional[int | str]):
        self.bot = bot
        self.chat_id = int(chat_id) if chat_id else None
        self.logger = logging.getLogger("telegram_events")
        self.dispatcher: Optional[TelegramLogDispatcher] = None
        if self.chat_id is not None:
            self.dispatcher = TelegramLogDispatcher(bot, self.chat_id)

    async def start(self) -> None:
        if self.dispatcher is not None:
            await self.dispatcher.start()

    async def stop(self) -> None:
        if self.dispatcher is not None:
            await self.dispatcher.stop()

    async def log_new_user(self, user_id: int, username: Optional[str], first_name: str) -> None:
        message = f"👤 <b>Новый пользователь</b>\n\n{_format_user_info(user_id, first_name, username)}"
        await self._send_event(message)

    async def log_subscription_purchase(
        self, user_id: int, username: Optional[str], first_name: str, plan: str, amount: int
    ) -> None:
        plan_readable = PLAN_NAMES.get(plan, plan)
        message = (
            f"💰 <b>Покупка подписки</b>\n\n"
            f"{_format_user_info(user_id, first_name, username)}\n"
            f"План: {html_decoration.quote(plan_readable)}\n"
            f"Сумма: {amount}"
        )
        await self._send_event(message)

    async def log_subscription_expired(
        self, user_id: int, username: Optional[str], first_name: str, plan: str
    ) -> None:
        plan_readable = PLAN_NAMES.get(plan, plan)
        message = (
            f"⏰ <b>Подписка истекла</b>\n\n"
            f"{_format_user_info(user_id, first_name, username)}\n"
            f"План: {html_decoration.quote(plan_readable)}"
        )
        await self._send_event(message)

    async def log_message_sent(
        self,
        sender_id: int,
        sender_username: Optional[str],
        sender_name: str,
        recipient_id: int,
        recipient_name: str,
        recipient_username: Optional[str],
        original_message: Message,
        message_text: Optional[str] = None,
        message_type: str = "text",
    ) -> Optional[Message]:
        sender_name_safe = html_decoration.quote(sender_name) if sender_name else "Неизвестно"
        sender_user = f"@{html_decoration.quote(sender_username)}" if sender_username else "нет"
        recipient_name_safe = html_decoration.quote(recipient_name) if recipient_name else "Неизвестно"
        recipient_user = f"@{html_decoration.quote(recipient_username)}" if recipient_username else "нет"
        info_message = (
            "📨 <b>Сообщение отправлено</b>\n"
            f"<b>От:</b> {sender_name_safe} (<code>{sender_id}</code>, {sender_user})\n"
            f"<b>Кому:</b> {recipient_name_safe} (<code>{recipient_id}</code>, {recipient_user})\n"
            f"<b>Тип:</b> {_escape(message_type)}"
        )
        return await self._send_event(info_message, message_to_forward=original_message)

    async def log_link_click(self, user_id: int, link_owner_id: int, custom_param: Optional[str] = None) -> None:
        message = f"🔗 <b>Переход по ссылке</b>\n\n<b>Владелец:</b> <code>{link_owner_id}</code>"
        if user_id:
            message += f"\n<b>Кликнул:</b> <code>{user_id}</code>"
        if custom_param:
            message += f"\n<b>Параметр:</b> {_escape(custom_param)}"
        await self._send_event(message)

    async def log_custom_link_set(
        self, user_id: int, username: Optional[str], first_name: str, custom_param: str
    ) -> None:
        message = (
            "🔄 <b>Установлена кастомная ссылка</b>\n\n"
            f"{_format_user_info(user_id, first_name, username)}\n"
            f"<b>Параметр:</b> {_escape(custom_param)}"
        )
        await self._send_event(message)

    async def log_error(
        self,
        error: Exception,
        context: str = "",
        action: str = "",
        update_info: str = "",
    ) -> None:
        message = format_error_message(
            error,
            context=context,
            action=action,
            update_info=update_info,
        )
        logger.error(
            "%s | context=%s | action=%s | update=%s",
            type(error).__name__,
            context or "unknown",
            action or "unknown",
            update_info or "unknown",
            exc_info=error,
        )
        await self._send_event(message)

    async def _send_event(
        self, message: str, message_to_forward: Optional[Message] = None
    ) -> Optional[Message]:
        if self.dispatcher is None:
            return None
        event = TelegramLogEvent(
            text=_truncate(message, MAX_TELEGRAM_LOG_LENGTH),
            message_to_forward=message_to_forward,
        )
        await self.dispatcher.enqueue(event)
        # Preserve the old contract: the channel send itself is asynchronous.
        return None
