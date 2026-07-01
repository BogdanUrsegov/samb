# bot/utils/send_main_mess.py

import logging
from typing import Callable
from aiogram.enums import ParseMode
from bot.database.utils import get_user
from bot.keyboards import create_share_keyboard
from bot.utils.create_link import create_link

logger = logging.getLogger(__name__)


async def send_main_mess(
    send_func: Callable,
    bot_username: str,
    user_id: int
) -> None:
    """
    Отправляет главное приветственное сообщение с личной ссылкой пользователя.
    
    Args:
        send_func: Функция отправки (message.answer или message.edit_text)
        bot_username: Юзернейм бота
        user_id: ID пользователя
        disable_link_preview: Отключать ли превью ссылок
    """
    try:
        user = await get_user(user_id)
        if not user:
            logger.error(f"User {user_id} not found in send_main_mess")
            await send_func(
                "⚙️ Не удалось загрузить ваши данные. Попробуйте /start",
                parse_mode=ParseMode.HTML
            )
            return

        user_link = await create_link(user_id, bot_username)

        text = (
            "🔗 <b>Вот твоя личная ссылка:</b>\n\n"
            f"<i>{user_link}</i>\n\n"
            "📱 Скопируй и опубликуй её в <b>Telegram</b>, <b>TikTok</b>, <b>VK</b>, <b>Instagram</b> "
            "и получай анонимные сообщения!\n\n"
        )

        await send_func(
            text,
            disable_link_preview=True,
            reply_markup=create_share_keyboard(user_link)
        )
        
        logger.debug(f"Main message sent to user {user_id}")
        
    except Exception as e:
        logger.exception(f"Error in send_main_mess for user {user_id}: {e}")
        await send_func(
            "⚙️ Произошла ошибка. Попробуйте ещё раз.",
            parse_mode=ParseMode.HTML
        )