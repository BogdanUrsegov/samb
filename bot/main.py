import asyncio
import logging

from aiogram.types import ErrorEvent

from bot.admin import admin_router
from bot.config import settings
from bot.database.session import engine, init_db
from bot.create_bot import bot, dp, event_logger
from .handlers import router
from .referrals import router as referrals_router

logger = logging.getLogger(__name__)


@dp.errors()
async def handle_update_error(event: ErrorEvent):
    """Log unhandled update errors with handler/action and update context."""
    update = event.update
    user = getattr(update, "from_user", None)
    action = f"Telegram update from user {user.id}" if user else "Telegram update"

    try:
        await event_logger.log_error(
            event.exception,
            context="aiogram update handler",
            action=action,
            update_info=f"Update: {update.update_id}",
        )
    except Exception:
        logger.exception("Failed to report update error to Telegram")

    return True


async def main():
    try:
        logger.info("Initializing database")
        await init_db()

        dp.include_router(admin_router)
        dp.include_router(referrals_router)
        dp.include_router(router)

        # Start the single ordered dispatcher before any business event can be logged.
        await event_logger.start()

        me = await bot.get_me()
        logger.info("Bot started as @%s", me.username)
        try:
            await bot.send_message(settings.admin_id, "✅ Bot started")
        except Exception as exc:
            logger.warning("Failed to notify admin: %s", exc)

        await dp.start_polling(bot, skip_updates=True)
    except Exception as exc:
        logger.critical("Application startup/runtime failed", exc_info=True)
        try:
            await event_logger.log_error(
                exc,
                context="bot.main",
                action="startup or polling",
            )
        except Exception:
            logger.exception("Failed to report application error to Telegram")
        raise
    finally:
        # Drain accepted Telegram log events before closing the bot session.
        await event_logger.stop()
        await bot.session.close()
        await engine.dispose()
        logger.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown signal received")
