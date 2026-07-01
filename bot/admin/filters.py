from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery
import os

ADMIN_ID = int(os.getenv("ADMIN_ID"))

class IsAdmin(Filter):
    async def __call__(self, obj: Message | CallbackQuery) -> bool:
        user_id = obj.from_user.id
        if user_id == ADMIN_ID:
            return True
        if isinstance(obj, CallbackQuery):
            await obj.answer("⛔ Доступ запрещён", show_alert=True)
        return False