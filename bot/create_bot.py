import os
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from hashids import Hashids
from bot.utils.logger_handler import TelegramEventLogger

# 1. Читаем и валидируем
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
LOGS_CHANNEL_ID = os.getenv("LOGS_CHANNEL_ID")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

if not all([BOT_TOKEN, ADMIN_ID, LOGS_CHANNEL_ID]):
    raise ValueError("Missing required env vars: BOT_TOKEN, ADMIN_ID, LOGS_CHANNEL_ID")

# 2. Базовое логирование (применяем LOG_LEVEL)
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)

# 3. Компоненты бота
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage()) # В проде замени на RedisStorage


event_logger = TelegramEventLogger(bot, LOGS_CHANNEL_ID)

# Hashids
HASHIDS_SALT = os.getenv("HASHIDS_SALT", "secret")
hashids = Hashids(salt=HASHIDS_SALT, min_length=4)

__all__ = ["bot", "dp", "hashids", "ADMIN_ID", "event_logger"]