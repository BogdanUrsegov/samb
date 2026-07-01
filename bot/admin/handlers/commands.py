from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from bot.create_bot import ADMIN_ID
from bot.admin.keyboards import admin_menu_keyboard

router = Router()

@router.message(Command("admin_menu"))
async def admin_menu(message: Message):
    if message.from_user.id != int(ADMIN_ID):  # Замените на реальные ID администраторов
        await message.answer("❌ У вас нет доступа к админ-панели.")
        return
    await message.answer("👨‍💼 <b>Админ-панель</b>", reply_markup=admin_menu_keyboard())