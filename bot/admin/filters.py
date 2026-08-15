from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from bot.database.admins import is_admin, is_superadmin


class IsAdmin(BaseFilter):
    """Allow access to handlers registered on the admin router."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        allowed = bool(user and await is_admin(user.id))
        if not allowed and isinstance(event, CallbackQuery):
            await event.answer("❌ Нет прав", show_alert=True)
        return allowed


class IsSuperAdmin(BaseFilter):
    """Allow only the main administrator to manage other administrators."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        allowed = bool(user and await is_superadmin(user.id))
        if not allowed and isinstance(event, CallbackQuery):
            await event.answer("❌ Недостаточно прав", show_alert=True)
        return allowed
