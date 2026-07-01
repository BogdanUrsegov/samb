from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика пользователей", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📋 Список пользователей", callback_data="admin_users_list")],
        [InlineKeyboardButton(text="👤 Информация о пользователе", callback_data="admin_user_info")],
        [InlineKeyboardButton(text="⭐ Добавить VIP", callback_data="admin_add_vip")],
        [InlineKeyboardButton(text="❌ Удалить VIP", callback_data="admin_remove_vip")],
        [InlineKeyboardButton(text="🔗 Реферальные ссылки", callback_data="admin_referrals")],
        [InlineKeyboardButton(text="🗑️ Удалить пользователя", callback_data="admin_delete_user")],
        [InlineKeyboardButton(text="📄 Получить лог", callback_data="admin_get_log")],
    ])

def admin_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ])

def admin_stats_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 График роста", callback_data="admin_growth_chart")],
        [InlineKeyboardButton(text="📈 График сообщений", callback_data="admin_messages_chart")],
        [InlineKeyboardButton(text="📋 Список пользователей", callback_data="admin_users_list")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")],
    ])

def admin_messages_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Обновить статистику", callback_data="admin_messages_chart")],
        [InlineKeyboardButton(text="◀️ Вернуться в меню", callback_data="admin_back")],
    ])

def vip_plans_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Неделя", callback_data=f"admin_vip_weekly_{user_id}")],
        [InlineKeyboardButton(text="Месяц", callback_data=f"admin_vip_monthly_{user_id}")],
        [InlineKeyboardButton(text="Навсегда", callback_data=f"admin_vip_forever_{user_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")],
    ])

def user_actions_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Добавить VIP", callback_data=f"admin_add_vip_user_{user_id}")],
        [InlineKeyboardButton(text="❌ Удалить VIP", callback_data=f"admin_remove_vip_user_{user_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")],
    ])

def referral_list_keyboard(referrals: list) -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton(text="➕ Создать ссылку", callback_data="admin_create_referral")]]
    for ref in referrals:
        keyboard.append([InlineKeyboardButton(
            text=f"{ref['name']} ({ref['clicks']} переходов)",
            callback_data=f"admin_referral_{ref['id']}"
        )])
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def confirm_delete_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Да, удалить", callback_data=f"admin_confirm_delete_{user_id}")],
        [InlineKeyboardButton(text="🟢 Отмена", callback_data="admin_back")],
    ])