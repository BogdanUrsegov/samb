"""Public referral deep-link handler."""

import logging
import re

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import Message

from bot.database.utils import add_user_if_not_exists, get_referral_by_code, record_referral_click
from bot.utils.referrals import referral_code_from_payload
from bot.utils.send_main_mess import send_main_mess

logger = logging.getLogger(__name__)
router = Router()

_REFERRAL_START_RE = re.compile(r"^/start(?:@[A-Za-z0-9_]+)?\s+ref_[A-Za-z0-9_-]{1,60}$")


@router.message(
    CommandStart(deep_link=True),
    F.text.regexp(_REFERRAL_START_RE),
    StateFilter(None),
)
async def handle_referral_start(message: Message, bot: Bot):
    """Track /start ref_CODE without interfering with existing deep links."""
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

    is_new_user = await add_user_if_not_exists(
        user.id,
        user.first_name or "Пользователь",
        user.username,
        user.last_name,
    )
    if is_new_user:
        logger.info("New user %s arrived through referral '%s'", user.id, code)

    await record_referral_click(referral["id"], user.id)
    logger.info("Referral click processed: user=%s code=%s", user.id, code)

    await send_main_mess(
        send_func=message.answer,
        bot_username=(await bot.me()).username,
        user_id=user.id,
    )
