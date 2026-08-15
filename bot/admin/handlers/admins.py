from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.admin.keyboards import admin_back_keyboard, admin_manage_keyboard, admin_menu_keyboard
from bot.admin.states import AdminStates
from bot.database.admins import add_admin, get_admins, is_superadmin, remove_admin

router = Router()


async def _manage_text() -> str:
    admins = await get_admins()
    lines = ["👮 <b>Администраторы</b>", ""]
    for admin in admins:
        role = "👑 Главный" if admin["is_superadmin"] else "👤 Администратор"
        lines.append(f"{role}: <code>{admin['user_id']}</code>")
    return "\n".join(lines)


@router.callback_query(F.data == "admin_manage")
async def admin_manage(callback: CallbackQuery):
    if not await is_superadmin(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return
    await callback.message.edit_text(await _manage_text(), reply_markup=admin_manage_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_add")
async def admin_add_start(callback: CallbackQuery, state: FSMContext):
    if not await is_superadmin(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_for_admin_id)
    await callback.message.edit_text(
        "➕ <b>Добавление администратора</b>\n\nВведите Telegram ID пользователя:",
        reply_markup=admin_back_keyboard(),
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_admin_id)
async def admin_add_finish(message: Message, state: FSMContext):
    if not await is_superadmin(message.from_user.id):
        await state.clear()
        return
    try:
        user_id = int(message.text.strip())
        if user_id <= 0:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("❌ ID должен быть положительным числом. Попробуйте ещё раз.")
        return

    if await add_admin(user_id, message.from_user.id):
        text = f"✅ Администратор <code>{user_id}</code> добавлен."
    else:
        text = f"ℹ️ Пользователь <code>{user_id}</code> уже является администратором."
    await state.clear()
    await message.answer(text, reply_markup=admin_manage_keyboard())


@router.callback_query(F.data == "admin_remove")
async def admin_remove_start(callback: CallbackQuery, state: FSMContext):
    if not await is_superadmin(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_for_remove_admin_id)
    await callback.message.edit_text(
        "➖ <b>Удаление администратора</b>\n\nВведите Telegram ID пользователя:\n\n⚠️ Главного администратора удалить нельзя.",
        reply_markup=admin_back_keyboard(),
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_remove_admin_id)
async def admin_remove_finish(message: Message, state: FSMContext):
    if not await is_superadmin(message.from_user.id):
        await state.clear()
        return
    try:
        user_id = int(message.text.strip())
        if user_id <= 0:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("❌ ID должен быть положительным числом. Попробуйте ещё раз.")
        return

    admins = await get_admins()
    target = next((admin for admin in admins if admin["user_id"] == user_id), None)
    if target is None:
        text = f"ℹ️ Пользователь <code>{user_id}</code> не найден среди администраторов."
    elif target["is_superadmin"]:
        text = "❌ Главного администратора удалить нельзя."
    else:
        await remove_admin(user_id)
        text = f"✅ Администратор <code>{user_id}</code> удалён."

    await state.clear()
    await message.answer(text, reply_markup=admin_manage_keyboard())
