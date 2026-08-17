import asyncio
import unittest

from bot.utils.telegram_log_dispatcher import TelegramLogDispatcher, TelegramLogEvent


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, disable_notification=True):
        self.sent.append(("send", chat_id, text))

    async def forward_message(self, chat_id, from_chat_id, message_id, disable_notification=True):
        self.sent.append(("forward", chat_id, from_chat_id, message_id))


class TelegramLogDispatcherTests(unittest.IsolatedAsyncioTestCase):
    async def test_events_are_delivered_in_fifo_order(self):
        bot = FakeBot()
        dispatcher = TelegramLogDispatcher(bot, -100, send_delay=0)
        await dispatcher.start()

        await dispatcher.enqueue(TelegramLogEvent("first"))
        await dispatcher.enqueue(TelegramLogEvent("second"))
        await dispatcher.enqueue(TelegramLogEvent("third"))
        await dispatcher._queue.join()
        await dispatcher.stop()

        self.assertEqual(
            [entry[2] for entry in bot.sent],
            ["first", "second", "third"],
        )

    async def test_queue_applies_backpressure_instead_of_dropping_events(self):
        bot = FakeBot()
        dispatcher = TelegramLogDispatcher(bot, -100, send_delay=0, max_queue_size=1)
        await dispatcher.start()

        await dispatcher.enqueue(TelegramLogEvent("first"))
        await dispatcher.enqueue(TelegramLogEvent("second"))
        await dispatcher._queue.join()
        await dispatcher.stop()

        self.assertEqual(len(bot.sent), 2)
        self.assertEqual([entry[2] for entry in bot.sent], ["first", "second"])


if __name__ == "__main__":
    unittest.main()
