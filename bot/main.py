import asyncio
import logging
from bot.database.session import init_db, engine
from .handlers import router
from bot.admin import admin_router
from .create_bot import bot, ADMIN_ID, dp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True
)
logger = logging.getLogger(__name__)


async def main():
    try:
        # 1. Инициализация БД
        logger.info("🗄️ Initializing database...")
        await init_db()
        
        # 2. Подключение роутеров
        dp.include_router(admin_router)

        dp.include_router(router)
        
        # 3. Проверка и уведомление
        me = await bot.get_me()
        logger.info(f"🤖 Bot started as @{me.username}")
        try:
            await bot.send_message(ADMIN_ID, "✅ Bot started")
        except Exception as e:
            logger.warning(f"⚠️ Failed to notify admin: {e}")

        # 4. Запуск polling
        await dp.start_polling(bot, skip_updates=True)
        
    finally:
        # Корректное завершение в ТОМ ЖЕ loop
        await bot.session.close()
        await engine.dispose()
        logger.info("🛑 Bot stopped")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Shutdown signal received")