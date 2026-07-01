import logging
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from bot.admin.keyboards import admin_back_keyboard, user_actions_keyboard, vip_plans_keyboard
from bot.admin.states import AdminStates
from bot.database.utils import (
    get_user_stats,
    add_or_update_subscription,
    remove_subscription,
    delete_user_by_id,
)

logger = logging.getLogger(__name__)
router = Router()


@router.message(AdminStates.waiting_for_user_id)
async def process_user_id(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.reply("❌ Введите корректный ID", reply_markup=admin_back_keyboard())
        return
    
    user_id = int(message.text)
    stats = await get_user_stats(user_id)
    
    if not stats:
        await message.reply("❌ Пользователь не найден", reply_markup=admin_back_keyboard())
        await state.clear()
        return
    
    text = (
        f"👤 <b>Информация</b>\n\n"
        f"ID: <code>{user_id}</code>\n"
        f"Имя: {stats.get('first_name', 'N/A')}\n"
        f"Username: @{stats.get('username', 'N/A')}\n"
        f"Получено: {stats.get('messages_received', 0)}\n"
        f"Отправлено: {stats.get('messages_sent', 0)}\n"
        f"Кликов: {stats.get('link_clicks', 0)}"
    )
    
    await message.reply(text, reply_markup=user_actions_keyboard(user_id))
    await state.clear()


@router.message(AdminStates.waiting_for_vip_user)
async def process_vip_user(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.reply("❌ Введите ID пользователя", reply_markup=admin_back_keyboard())
        return
    
    user_id = int(message.text)
    
    await message.reply(
        f"⭐ <b>Выберите план VIP</b> для <code>{user_id}</code>:",
        reply_markup=vip_plans_keyboard(user_id)
    )
    await state.clear()  # План выбирается кнопкой, состояние не нужно


@router.message(AdminStates.waiting_for_remove_vip_user)
async def process_remove_vip(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.reply("❌ Введите ID", reply_markup=admin_back_keyboard())
        return
    
    user_id = int(message.text)
    await remove_subscription(user_id)
    await message.reply(f"❌ VIP удалён у <code>{user_id}</code>", reply_markup=admin_back_keyboard())
    await state.clear()


@router.message(AdminStates.waiting_for_delete_user)
async def process_delete_user(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.reply("❌ Введите ID", reply_markup=admin_back_keyboard())
        return
    
    user_id = int(message.text)
    await delete_user_by_id(user_id)
    await message.reply(f"🗑️ Пользователь <code>{user_id}</code> удалён", reply_markup=admin_back_keyboard())
    await state.clear()