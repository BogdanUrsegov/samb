from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from bot.database.admins import is_admin


class IsAdmin(BaseFilter):
    """Allows admin-router handlers only to users stored in admins."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return bool(user and await is_admin(user.id))
