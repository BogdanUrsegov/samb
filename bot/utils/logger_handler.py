"""
Модуль для отправки логов и бизнес-событий в Telegram канал.
"""

import asyncio
import logging
import sys
from typing import Optional

from aiogram import Bot
import traceback
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message
from aiogram.utils.formatting import html_decoration


logger = logging.getLogger(__name__)

# Константы для маппинга планов подписки
PLAN_NAMES = {
    "weekly": "Неделя",
    "monthly": "Месяц",
    "forever": "Навсегда",
}


def _format_user_info(user_id: int, first_name: Optional[str], username: Optional[str]) -> str:
    """Форматирует информацию о пользователе в HTML."""
    name = html_decoration.quote(first_name) if first_name else "Неизвестно"
    user = f"@{username}" if username else "нет"
    return f"ID: <code>{user_id}</code>\nИмя: {name}\nUsername: {user}"


class TelegramLoggerHandler(logging.Handler):
    """
    Асинхронный обработчик логов для отправки важных событий в Telegram.
    """

    def __init__(self, bot: Bot, chat_id: int, level: int = logging.INFO):
        super().__init__(level)
        self.bot = bot
        self.chat_id = chat_id
        self.formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        self._queue: asyncio.Queue[logging.LogRecord] = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None

    def emit(self, record: logging.LogRecord) -> None:
        """Добавляет запись лога в очередь."""
        try:
            self._queue.put_nowait(record)
        except RuntimeError:
            print("Failed to queue log: Event loop is not running", file=sys.stderr)

    async def start(self) -> None:
        """Запускает фоновую задачу обработки логов."""
        if not self._task:
            self._task = asyncio.create_task(self._process_logs())

    async def stop(self) -> None:
        """Останавливает обработчик логов через отмену задачи."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _process_logs(self) -> None:
        """Бесконечно обрабатывает очередь логов."""
        while True:
            record = await self._queue.get()
            try:
                message = self.format(record)
                await self.bot.send_message(self.chat_id, message)
            except TelegramAPIError as e:
                print(f"Failed to send log to Telegram: {e}", file=sys.stderr)
            except Exception as e:
                print(f"Error in Telegram logger: {e}", file=sys.stderr)
            finally:
                self._queue.task_done()


class TelegramEventLogger:
    """
    Класс для логирования бизнес-событий в Telegram канал.
    """

    def __init__(self, bot: Bot, chat_id: int):
        self.bot = bot
        self.chat_id = chat_id
        self.logger = logging.getLogger("telegram_events")

    async def log_new_user(self, user_id: int, username: Optional[str], first_name: str) -> None:
        """Логирует регистрацию нового пользователя."""
        message = (
            f"👤 <b>Новый пользователь</b>\n\n"
            f"{_format_user_info(user_id, first_name, username)}"
        )
        await self._send_event(message)

    async def log_subscription_purchase(
        self, user_id: int, username: Optional[str], first_name: str, plan: str, amount: int
    ) -> None:
        """Логирует покупку подписки."""
        plan_readable = PLAN_NAMES.get(plan, plan)
        message = (
            f"💰 <b>Покупка подписки</b>\n\n"
            f"{_format_user_info(user_id, first_name, username)}\n"
            f"План: {plan_readable}\n"
            f"Сумма: {amount} ⭐️"
        )
        await self._send_event(message)

    async def log_subscription_expired(
        self, user_id: int, username: Optional[str], first_name: str, plan: str
    ) -> None:
        """Логирует истечение подписки."""
        plan_readable = PLAN_NAMES.get(plan, plan)
        message = (
            f"⏰ <b>Подписка истекла</b>\n\n"
            f"{_format_user_info(user_id, first_name, username)}\n"
            f"План: {plan_readable}"
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
        """Логирует отправку сообщения, пересылая его содержимое."""
        sender_name_safe = html_decoration.quote(sender_name) if sender_name else "Неизвестно"
        sender_user = f"@{sender_username}" if sender_username else "нет"
        
        recipient_name_safe = html_decoration.quote(recipient_name) if recipient_name else "Неизвестно"
        recipient_user = f"@{recipient_username}" if recipient_username else "нет"

        info_message = (
            f"📨 <b>Сообщение отправлено</b>\n"
            f"<b>От:</b> {sender_name_safe} (<code>{sender_id}</code>, {sender_user})\n"
            f"<b>Кому:</b> {recipient_name_safe} (<code>{recipient_id}</code>, {recipient_user})\n"
            f"<b>Тип:</b> {html_decoration.quote(message_type)}"
        )
        
        return await self._send_event(info_message, message_to_forward=original_message)

    async def log_link_click(
        self, user_id: int, link_owner_id: int, custom_param: Optional[str] = None
    ) -> None:
        """Логирует переход по ссылке."""
        message = f"🔗 <b>Переход по ссылке</b>\n\n<b>Владелец:</b> <code>{link_owner_id}</code>"
        if user_id:
            message += f"\n<b>Кликнул:</b> <code>{user_id}</code>"
        if custom_param:
            message += f"\n<b>Параметр:</b> {html_decoration.quote(custom_param)}"
            
        await self._send_event(message)

    async def log_custom_link_set(
        self, user_id: int, username: Optional[str], first_name: str, custom_param: str
    ) -> None:
        """Логирует установку кастомной ссылки."""
        message = (
            f"🔄 <b>Установлена кастомная ссылка</b>\n\n"
            f"{_format_user_info(user_id, first_name, username)}\n"
            f"<b>Параметр:</b> {html_decoration.quote(custom_param)}"
        )
        await self._send_event(message)

    async def _send_event(
        self, message: str, message_to_forward: Optional[Message] = None
    ) -> Optional[Message]:
        """Отправляет событие в канал логов, опционально пересылая сообщение."""
        try:
            if message_to_forward:
                try:
                    await self.bot.forward_message(
                        chat_id=self.chat_id,
                        from_chat_id=message_to_forward.chat.id,
                        message_id=message_to_forward.message_id,
                        disable_notification=True,
                    )
                except TelegramAPIError as e:
                    self.logger.error(f"Failed to forward message: {e}")

            return await self.bot.send_message(
                chat_id=self.chat_id, 
                text=message
            )
        except Exception as e:
            self.logger.error(f"Failed to send event to Telegram: {e}")
            return None
        
    async def log_error(self, error: Exception, context: str = ""):
        error_type = type(error).__name__
        error_message = str(error)
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        
        # Обрезаем traceback, если слишком длинный
        if len(tb) > 3500:
            tb = tb[:3500] + "\n... (обрезано)"
        
        message = (
            f"❌ <b>Ошибка</b>\n\n"
            f"<b>Тип:</b> <code>{error_type}</code>\n"
            f"<b>Сообщение:</b> <code>{html_decoration.quote(error_message)}</code>\n"
        )
        
        if context:
            message += f"<b>Контекст:</b> {html_decoration.quote(context)}\n"
        
        message += f"\n<b>Traceback:</b>\n<pre>{html_decoration.quote(tb)}</pre>"
        
        logger.error(message)
        await self._send_event(message)