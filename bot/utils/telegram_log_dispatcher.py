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
MAX_BACKOFF_DELAY = 10.0


@dataclass(slots=True)
class TelegramLogEvent:
    """One channel event with independent delivery state for forwarded content."""

    text: str
    message_to_forward: Optional[Message] = None
    forward_delivered: bool = False


class TelegramLogDispatcher:
    """Serialize Telegram log events and protect delivery from API flooding."""

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
        """Start the single delivery task; safe to call repeatedly."""
        if self._task is not None and not self._task.done():
            return
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name="telegram-log-dispatcher")

    async def stop(self) -> None:
        """Stop after all accepted events have been processed."""
        self._stopping = True
        task = self._task
        if task is None:
            return

        try:
            # join() waits for the event currently being delivered as well as all
            # queued events. Do not cancel the worker before this completes.
            await self._queue.join()
        finally:
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            finally:
                self._task = None

    async def enqueue(self, event: TelegramLogEvent) -> bool:
        """Queue an event, applying backpressure instead of dropping it."""
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
                delivered = await self._deliver(event)
                if not delivered:
                    logger.error(
                        "Telegram log event was not delivered after %d attempts; "
                        "continuing with the next event",
                        MAX_RETRIES,
                    )
                elif self.send_delay:
                    await asyncio.sleep(self.send_delay)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected Telegram log dispatcher error")
            finally:
                self._queue.task_done()

    async def _deliver(self, event: TelegramLogEvent) -> bool:
        """Deliver one event without repeating an already successful forward."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if event.message_to_forward is not None and not event.forward_delivered:
                    await self.bot.forward_message(
                        chat_id=self.chat_id,
                        from_chat_id=event.message_to_forward.chat.id,
                        message_id=event.message_to_forward.message_id,
                        disable_notification=True,
                    )
                    # Only mark it delivered after Telegram has acknowledged the
                    # request. A later retry therefore cannot duplicate a known-
                    # successful forward within this process.
                    event.forward_delivered = True

                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=event.text,
                    disable_notification=True,
                )
                return True
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
                    logger.exception(
                        "Telegram log delivery failed after %d attempts",
                        MAX_RETRIES,
                    )
                    return False
                delay = min(2 ** (attempt - 1), MAX_BACKOFF_DELAY)
                logger.warning(
                    "Telegram log delivery failed; retry in %.1fs (attempt %d/%d)",
                    delay,
                    attempt,
                    MAX_RETRIES,
                    exc_info=True,
                )
                await asyncio.sleep(delay)
        return False
