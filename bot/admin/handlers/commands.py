from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from bot.admin.keyboards import admin_menu_keyboard
from bot.database.admins import is_superadmin

router = Router()


@router.message(Command("admin_menu"))
async def admin_menu(message: Message):
    await message.answer(
        "👨‍💼 <b>Админ-панель</b>",
        reply_markup=admin_menu_keyboard(await is_superadmin(message.from_user.id)),
    )
