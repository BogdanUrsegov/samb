import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from bot.admin.keyboards import (
    admin_menu_keyboard, admin_back_keyboard, admin_stats_keyboard,
    admin_messages_menu_keyboard, vip_plans_keyboard,
    user_actions_keyboard, referral_list_keyboard, confirm_delete_keyboard
)
from bot.admin.states import AdminStates
from bot.database.utils import (
    count_all_users, get_all_user_ids,
    add_or_update_subscription, remove_subscription, delete_user_by_id,
    get_subscription, get_user_growth_data, get_message_count_data,
)
from bot.utils.charts import generate_user_growth_chart, generate_message_count_chart

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("👨‍ <b>Админ-панель</b>\n\nВыберите действие:", reply_markup=admin_menu_keyboard())
    await callback.answer()

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    try:
        total = await count_all_users()
        
        # Получаем статистику по подпискам
        from bot.database.utils import get_subscription_plans
        subs = await get_subscription_plans()
        vip_count = subs.get("weekly", 0) + subs.get("monthly", 0) + subs.get("forever", 0)
        
        text = (
            f"📊 <b>Статистика бота</b>\n\n"
            f"👥 Всего пользователей: <b>{total}</b>\n"
            f"⭐ Пользователей с VIP: <b>{vip_count}</b>\n\n"
            f"<b>Подписки по планам:</b>\n"
            f"🔹 Неделя: {subs.get('weekly', 0)}\n"
            f"🔹 Месяц: {subs.get('monthly', 0)}\n"
            f"🔹 Навсегда: {subs.get('forever', 0)}"
        )
        
        await callback.message.edit_text(text, reply_markup=admin_stats_keyboard())
        await callback.answer()
    except Exception as e:
        logger.exception(f"Error in admin_stats: {e}")
        await callback.answer("❌ Ошибка при получении статистики", show_alert=True)

@router.callback_query(F.data == "admin_users_list")
async def admin_users_list(callback: CallbackQuery, bot: Bot):
    try:
        user_ids = await get_all_user_ids()
        
        if not user_ids:
            await callback.answer("📂 База пуста", show_alert=True)
            return
        
        # Создаем файл со списком ID
        ids_text = "\n".join(str(uid) for uid in user_ids)
        file = BufferedInputFile(ids_text.encode("utf-8"), filename="user_ids.txt")
        
        await callback.message.edit_text(
            f"📋 <b>Список пользователей</b>\n\nВсего: <b>{len(user_ids)}</b>\n\nФайл отправлен ниже ⬇️",
            reply_markup=admin_back_keyboard()
        )
        await bot.send_document(
            callback.message.chat.id,
            file,
            caption=f"📄 ID пользователей ({len(user_ids)} шт.)"
        )
        await callback.answer()
    except Exception as e:
        logger.exception(f"Error in admin_users_list: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data == "admin_user_info")
async def admin_user_info(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_user_id)
    await callback.message.edit_text(
        "👤 <b>Информация о пользователе</b>\n\nВведите ID пользователя:",
        reply_markup=admin_back_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "admin_add_vip")
async def admin_add_vip(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_vip_user)
    await callback.message.edit_text(
        "⭐ <b>Добавление VIP</b>\n\nВведите ID пользователя:",
        reply_markup=admin_back_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "admin_remove_vip")
async def admin_remove_vip(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_remove_vip_user)
    await callback.message.edit_text(
        "❌ <b>Удаление VIP</b>\n\nВведите ID пользователя:",
        reply_markup=admin_back_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "admin_delete_user")
async def admin_delete_user(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_delete_user)
    await callback.message.edit_text(
        "🗑️ <b>Удаление пользователя</b>\n\n⚠️ <b>ВНИМАНИЕ:</b> Это действие необратимо!\n\nВведите ID пользователя:",
        reply_markup=admin_back_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin_vip_"))
async def admin_set_vip(callback: CallbackQuery):
    try:
        parts = callback.data.split("_")
        plan = parts[2]
        user_id = int(parts[3])
        
        await add_or_update_subscription(user_id, plan)
        
        await callback.message.edit_text(
            f"✅ <b>VIP добавлен</b>\n\n"
            f"Пользователь: <code>{user_id}</code>\n"
            f"План: <b>{plan}</b>",
            reply_markup=admin_back_keyboard()
        )
        await callback.answer("✅ Готово!")
    except Exception as e:
        logger.exception(f"Error in admin_set_vip: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data.startswith("admin_add_vip_user_"))
async def admin_add_vip_user(callback: CallbackQuery):
    try:
        user_id = int(callback.data.split("_")[-1])
        await callback.message.edit_text(
            f"⭐ <b>Выберите план VIP</b> для пользователя <code>{user_id}</code>:",
            reply_markup=vip_plans_keyboard(user_id)
        )
        await callback.answer()
    except Exception as e:
        logger.exception(f"Error in admin_add_vip_user: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data.startswith("admin_remove_vip_user_"))
async def admin_remove_vip_user(callback: CallbackQuery):
    try:
        user_id = int(callback.data.split("_")[-1])
        await remove_subscription(user_id)
        
        await callback.message.edit_text(
            f"❌ <b>VIP удалён</b>\n\nПользователь: <code>{user_id}</code>",
            reply_markup=admin_back_keyboard()
        )
        await callback.answer()
    except Exception as e:
        logger.exception(f"Error in admin_remove_vip_user: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data.startswith("admin_confirm_delete_"))
async def admin_confirm_delete(callback: CallbackQuery):
    try:
        user_id = int(callback.data.split("_")[-1])
        await delete_user_by_id(user_id)
        
        await callback.message.edit_text(
            f"🗑️ <b>Пользователь удалён</b>\n\nID: <code>{user_id}</code>",
            reply_markup=admin_back_keyboard()
        )
        await callback.answer()
    except Exception as e:
        logger.exception(f"Error in admin_confirm_delete: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data == "admin_get_log")
async def admin_get_log(callback: CallbackQuery, bot: Bot):
    try:
        from aiogram.types import FSInputFile
        log_file = FSInputFile("/path/to/your/bot.log")  # ← УКАЖИ ПУТЬ К ЛОГУ
        await bot.send_document(callback.message.chat.id, log_file, caption="📄 Лог-файл")
        await callback.answer()
    except Exception as e:
        logger.exception(f"Error in admin_get_log: {e}")
        await callback.answer("❌ Ошибка при получении лога", show_alert=True)

@router.callback_query(F.data == "admin_referrals")
async def admin_referrals(callback: CallbackQuery):
    try:
        from bot.database.utils import get_all_referral_links
        referrals = await get_all_referral_links()
        
        await callback.message.edit_text(
            "🔗 <b>Реферальные ссылки</b>\n\nВыберите ссылку или создайте новую:",
            reply_markup=referral_list_keyboard(referrals)
        )
        await callback.answer()
    except Exception as e:
        logger.exception(f"Error in admin_referrals: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data == "admin_growth_chart")
async def admin_growth_chart(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer("📊 Генерирую график...")
        
        # Получаем данные за 7 дней
        growth_data = await get_user_growth_data(days=7)
        
        # Генерируем график
        chart_buf = await generate_user_growth_chart(growth_data)
        chart_file = BufferedInputFile(chart_buf.getvalue(), filename="user_growth.png")
        
        # Отправляем график
        await bot.send_photo(
            callback.message.chat.id,
            chart_file,
            caption="📊 <b>График роста пользователей за неделю</b>"
        )
        
        # Отправляем файл со списком ID
        user_ids = await get_all_user_ids()
        ids_text = "\n".join(str(uid) for uid in user_ids)
        file = BufferedInputFile(ids_text.encode("utf-8"), filename="user_ids.txt")
        await bot.send_document(
            callback.message.chat.id,
            file,
            caption=f"📄 Список ID ({len(user_ids)} шт.)"
        )
        
        # Отправляем меню
        await callback.message.answer(
            "📊 <b>Статистика</b>\n\nВыберите действие:",
            reply_markup=admin_stats_keyboard()
        )
    except Exception as e:
        logger.exception(f"Error in admin_growth_chart: {e}")
        await callback.answer("❌ Ошибка при генерации графика", show_alert=True)

@router.callback_query(F.data == "admin_messages_chart")
async def admin_messages_chart(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer("📈 Генерирую график...")
        
        # Получаем данные за 7 дней
        messages_data = await get_message_count_data(days=7)
        
        # Генерируем график
        chart_buf = await generate_message_count_chart(messages_data)
        chart_file = BufferedInputFile(chart_buf.getvalue(), filename="messages.png")
        
        # Отправляем график
        await bot.send_photo(
            callback.message.chat.id,
            chart_file,
            caption="📈 <b>График отправленных сообщений за неделю</b>"
        )
        
        # Отправляем меню
        await callback.message.answer(
            "📊 <b>Статистика сообщений</b>\n\nВыберите действие:",
            reply_markup=admin_messages_menu_keyboard()
        )
    except Exception as e:
        logger.exception(f"Error in admin_messages_chart: {e}")
        await callback.answer("❌ Ошибка при генерации графика", show_alert=True)