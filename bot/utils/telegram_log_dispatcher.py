"""Reliable, throttled FIFO delivery of Telegram event logs."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.types import Message

logger = logging.getLogger(__name__)

DEFAULT_SEND_DELAY = 0.12
MAX_QUEUE_SIZE = 2000
MAX_RETRIES = 5


@dataclass(slots=True)
class TelegramLogEvent:
    """One atomic channel event: optional forwarded message + text notification."""

    text: str
    message_to_forward: Optional[Message] = None


class TelegramLogDispatcher:
    """Serializes Telegram channel events and applies backoff on API throttling."""

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        *,
        send_delay: float = DEFAULT_SEND_DELAY,
        max_queue_size: int = MAX_QUEUE_SIZE,
    ) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self.send_delay = max(0.0, send_delay)
        self._queue: asyncio.Queue[TelegramLogEvent] = asyncio.Queue(maxsize=max_queue_size)
        self._task: Optional[asyncio.Task[None]] = None
        self._stopping = False

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping = False
            self._task = asyncio.create_task(self._run(), name="telegram-log-dispatcher")

    async def stop(self) -> None:
        self._stopping = True
        task = self._task
        if task is None:
            return

        # Drain already accepted events before shutting down.
        if not self._queue.empty():
            await self._queue.join()

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def enqueue(self, event: TelegramLogEvent) -> bool:
        """Accept an event without bypassing the global delivery order."""
        if self._stopping:
            logger.warning("Telegram log dispatcher is stopping; event was not queued")
            return False

        if self._task is None or self._task.done():
            await self.start()

        try:
            await self._queue.put(event)
            return True
        except asyncio.CancelledError:
            return False

    async def _run(self) -> None:
        while True:
            event = await self._queue.get()
            try:
                await self._deliver_with_retry(event)
                if self.send_delay:
                    await asyncio.sleep(self.send_delay)
            except asyncio.CancelledError:
                # Do not silently lose an event during normal shutdown; the queue
                # is drained by stop() before cancellation.
                raise
            except Exception:
                logger.exception("Unexpected Telegram log dispatcher error")
            finally:
                self._queue.task_done()

    async def _deliver_with_retry(self, event: TelegramLogEvent) -> None:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if event.message_to_forward is not None:
                    await self.bot.forward_message(
                        chat_id=self.chat_id,
                        from_chat_id=event.message_to_forward.chat.id,
                        message_id=event.message_to_forward.message_id,
                        disable_notification=True,
                    )

                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=event.text,
                    disable_notification=True,
                )
                return
            except TelegramRetryAfter as exc:
                delay = max(float(exc.retry_after), self.send_delay)
                logger.warning(
                    "Telegram log delivery throttled; retry in %.2fs (attempt %d/%d)",
                    delay,
                    attempt,
                    MAX_RETRIES,
                )
                await asyncio.sleep(delay)
            except TelegramAPIError:
                if attempt >= MAX_RETRIES:
                    raise
                delay = min(2 ** (attempt - 1), 10)
                logger.warning(
                    "Telegram log delivery failed; retry in %ds (attempt %d/%d)",
                    delay,
                    attempt,
                    MAX_RETRIES,
                    exc_info=True,
                )
                await asyncio.sleep(delay)
