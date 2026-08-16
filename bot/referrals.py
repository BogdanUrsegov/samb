"""Public referral deep-link handler and assigned-viewer statistics."""

import logging
import re

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import CallbackQuery, Message

from bot.database.utils import (
    add_user_if_not_exists,
    get_referral_by_code,
    get_referral_stats,
    record_referral_click,
)
from bot.utils.referral_ui import format_referral_stats, referral_stats_keyboard
from bot.utils.referrals import referral_code_from_payload, referral_payload
from bot.utils.send_main_mess import send_main_mess

logger = logging.getLogger(__name__)
router = Router()

_REFERRAL_START_RE = re.compile(r"^/start(?:@[A-Za-z0-9_]+)?\s+ref_[A-Za-z0-9_]{1,60}$")


async def _render_viewer_referral(callback: CallbackQuery, bot: Bot, referral_id: int) -> bool:
    """Refresh the referral statistics screen for its assigned viewer."""
    referral = await get_referral_stats(referral_id)
    if not referral or referral.get("viewer_id") != callback.from_user.id:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return False

    bot_username = (await bot.me()).username
    link = f"https://t.me/{bot_username}?start={referral_payload(referral['code'])}"
    try:
        await callback.message.edit_text(
            format_referral_stats(referral, link),
            reply_markup=referral_stats_keyboard(referral_id, admin=False),
            disable_web_page_preview=True,
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
    return True


@router.message(
    CommandStart(deep_link=True),
    F.text.regexp(_REFERRAL_START_RE),
    StateFilter(None),
)
async def handle_referral_start(message: Message, bot: Bot):
    """Track /start ref_CODE and show stats to the assigned viewer."""
    user = message.from_user
    parts = (message.text or "").split(maxsplit=1)
    payload = parts[1] if len(parts) == 2 else ""
    code = referral_code_from_payload(payload)

    if not code:
        return

    referral = await get_referral_by_code(code)
    if not referral:
        logger.info("Unknown or inactive referral code '%s' from user %s", code, user.id)
        await send_main_mess(
            send_func=message.answer,
            bot_username=(await bot.me()).username,
            user_id=user.id,
        )
        return

    # A referral click is counted only for a genuinely new bot user.
    # Existing users must not become referral conversions merely by opening the link.
    is_new_user = await add_user_if_not_exists(
        user.id,
        user.first_name or "Пользователь",
        user.username,
        user.last_name,
    )
    if is_new_user:
        await record_referral_click(referral["id"], user.id)
        logger.info("New referral click processed: user=%s code=%s", user.id, code)
    else:
        logger.info("Existing bot user opened referral link: user=%s code=%s; click not counted", user.id, code)

    # The assigned viewer gets the same read-only statistics screen as the admin.
    # Other users continue through the normal start flow.
    if referral.get("viewer_id") == user.id:
        stats = await get_referral_stats(referral["id"])
        bot_username = (await bot.me()).username
        link = f"https://t.me/{bot_username}?start={referral_payload(code)}"
        await message.answer(
            format_referral_stats(stats, link),
            reply_markup=referral_stats_keyboard(referral["id"], admin=False),
            disable_web_page_preview=True,
        )
        return

    await send_main_mess(
        send_func=message.answer,
        bot_username=(await bot.me()).username,
        user_id=user.id,
    )