import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from hashids import Hashids

from bot.config import settings
from bot.utils.logger_handler import TelegramEventLogger

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)

bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())
event_logger = TelegramEventLogger(bot, settings.logs_channel_id)
hashids = Hashids(salt=settings.hashids_salt, min_length=4)

# Backward-compatible exports for existing modules.
BOT_TOKEN = settings.bot_token
ADMIN_ID = settings.admin_id
LOGS_CHANNEL_ID = settings.logs_channel_id
HASHIDS_SALT = settings.hashids_salt

__all__ = ["bot", "dp", "hashids", "ADMIN_ID", "event_logger"]
