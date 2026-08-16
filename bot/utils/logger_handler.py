"""Logging of application errors and business events to Telegram."""

import asyncio
import logging
import sys
import traceback
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message
from aiogram.utils.formatting import html_decoration

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
    tb = error.__traceback__
    if tb is not None:
        frames = traceback.extract_tb(tb)
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
        tb_text = _truncate(tb_text, MAX_TRACEBACK_LENGTH)
        lines.append(f"<pre>{_escape(tb_text)}</pre>")

    return _truncate("\n".join(lines), MAX_TELEGRAM_LOG_LENGTH)


class TelegramLoggerHandler(logging.Handler):
    """Asynchronously sends WARNING/ERROR records to the Telegram log channel."""

    def __init__(self, bot: Bot, chat_id: int, level: int = logging.WARNING):
        super().__init__(level)
        self.bot = bot
        self.chat_id = chat_id
        self._queue: asyncio.Queue[logging.LogRecord] = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._queue.put_nowait(record)
        except RuntimeError:
            print("Failed to queue Telegram log: event loop is not running", file=sys.stderr)

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._process_logs())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _process_logs(self) -> None:
        while True:
            record = await self._queue.get()
            try:
                message = self.format(record)
                await self.bot.send_message(self.chat_id, message, disable_notification=True)
            except TelegramAPIError as exc:
                print(f"Failed to send Telegram log: {exc}", file=sys.stderr)
            except Exception as exc:
                print(f"Telegram logger failed: {exc}", file=sys.stderr)
            finally:
                self._queue.task_done()


class TelegramEventLogger:
    """Sends compact business events and application errors to a Telegram channel."""

    def __init__(self, bot: Bot, chat_id: Optional[int | str]):
        self.bot = bot
        self.chat_id = int(chat_id) if chat_id else None
        self.logger = logging.getLogger("telegram_events")

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
            f"Сумма: {amount} ⭐️"
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
        if self.chat_id is None:
            return None
        try:
            if message_to_forward:
                try:
                    await self.bot.forward_message(
                        chat_id=self.chat_id,
                        from_chat_id=message_to_forward.chat.id,
                        message_id=message_to_forward.message_id,
                        disable_notification=True,
                    )
                except TelegramAPIError as exc:
                    self.logger.warning("Could not forward event message: %s", exc)
            return await self.bot.send_message(
                chat_id=self.chat_id,
                text=_truncate(message, MAX_TELEGRAM_LOG_LENGTH),
                disable_notification=True,
            )
        except Exception as exc:
            self.logger.error("Failed to send event to Telegram: %s", exc)
            return None
