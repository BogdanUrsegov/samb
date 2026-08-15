import logging
import re
from decimal import Decimal, InvalidOperation

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.admin.filters import IsSuperAdmin
from bot.admin.keyboards import (
    admin_back_keyboard,
    admin_manage_back_keyboard,
    admin_manage_keyboard,
    admin_menu_keyboard,
    admin_stats_keyboard,
    referral_list_keyboard,
    user_actions_keyboard,
    vip_plans_keyboard,
)
from bot.admin.states import AdminStates
from bot.database.admins import add_admin, get_admins, remove_admin
from bot.database.utils import (
    add_or_update_subscription,
    add_user_if_not_exists,
    count_all_users,
    create_referral_link,
    delete_user_by_id,
    get_all_referral_links,
    get_all_user_ids,
    get_message_count_data,
    get_referral_by_code,
    get_referral_stats,
    get_subscription_plans,
    get_user_growth_data,
    get_user_stats,
    remove_subscription,
)
from bot.utils.charts import generate_message_count_chart, generate_user_growth_chart
from bot.utils.referral_ui import format_referral_stats, referral_stats_keyboard
from bot.utils.referrals import normalize_referral_code, referral_payload

logger = logging.getLogger(__name__)
router = Router()
superadmin_router = Router()
superadmin_router.callback_query.filter(IsSuperAdmin())
superadmin_router.message.filter(IsSuperAdmin())


async def _notify_user(bot: Bot, user_id: int, text: str) -> None:
    try:
        await bot.send_message(user_id, text)
    except TelegramAPIError as exc:
        logger.info("Не удалось отправить уведомление пользователю %s: %s", user_id, exc)


async def _edit_menu(callback: CallbackQuery, text: str, markup) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def _admin_menu(callback: CallbackQuery) -> None:
    admins = await get_admins()
    is_superadmin = any(
        admin["user_id"] == callback.from_user.id and admin["is_superadmin"]
        for admin in admins
    )
    await _edit_menu(
        callback,
        "👨‍💼 <b>Админ-панель</b>\n\nВыберите действие:",
        admin_menu_keyboard(is_superadmin),
    )


@router.message(F.text == "/admin_menu")
async def admin_menu(message: Message):
    admins = await get_admins()
    is_superadmin = any(
        admin["user_id"] == message.from_user.id and admin["is_superadmin"]
        for admin in admins
    )
    await message.answer(
        "👨‍💼 <b>Админ-панель</b>",
        reply_markup=admin_menu_keyboard(is_superadmin),
    )


@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await _admin_menu(callback)
    await callback.answer()


@superadmin_router.callback_query(F.data == "admin_manage")
async def admin_manage(callback: CallbackQuery):
    await _edit_menu(
        callback,
        await _manage_text(),
        admin_manage_keyboard(),
    )
    await callback.answer()


@superadmin_router.callback_query(F.data == "admin_manage_back")
async def admin_manage_back(callback: CallbackQuery):
    await _edit_menu(
        callback,
        await _manage_text(),
        admin_manage_keyboard(),
    )
    await callback.answer()


async def _manage_text() -> str:
    admins = await get_admins()
    lines = ["👮 <b>Администраторы</b>", ""]
    for admin in admins:
        role = "👑 Главный" if admin["is_superadmin"] else "👤 Администратор"
        lines.append(f"{role}: <code>{admin['user_id']}</code>")
    return "\n".join(lines)


@superadmin_router.callback_query(F.data == "admin_add")
async def admin_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_admin_id)
    await callback.message.edit_text(
        "➕ <b>Добавление администратора</b>\n\nВведите Telegram ID пользователя:",
        reply_markup=admin_manage_back_keyboard(),
    )
    await callback.answer()


@superadmin_router.message(AdminStates.waiting_for_admin_id)
async def admin_add_finish(message: Message, state: FSMContext, bot: Bot):
    try:
        user_id = int((message.text or "").strip())
        if user_id <= 0:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("❌ ID должен быть положительным числом. Попробуйте ещё раз.")
        return

    added = await add_admin(user_id, message.from_user.id)
    if added:
        await _notify_user(
            bot,
            user_id,
            "👮 <b>Вам предоставлен доступ к админ-панели.</b>\n\nТеперь вам доступен административный раздел бота.",
        )
        text = f"✅ Администратор <code>{user_id}</code> добавлен."
    else:
        text = f"ℹ️ Пользователь <code>{user_id}</code> уже является администратором."
    await state.clear()
    await message.answer(text, reply_markup=admin_manage_keyboard())


@superadmin_router.callback_query(F.data == "admin_remove")
async def admin_remove_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_remove_admin_id)
    await callback.message.edit_text(
        "➖ <b>Удаление администратора</b>\n\nВведите Telegram ID пользователя:\n\n⚠️ Главного администратора удалить нельзя.",
        reply_markup=admin_manage_back_keyboard(),
    )
    await callback.answer()


@superadmin_router.message(AdminStates.waiting_for_remove_admin_id)
async def admin_remove_finish(message: Message, state: FSMContext, bot: Bot):
    try:
        user_id = int((message.text or "").strip())
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
        await _notify_user(
            bot,
            user_id,
            "⚠️ <b>Ваш доступ к админ-панели был удалён.</b>\n\nВы больше не можете использовать административный раздел бота.",
        )
        text = f"✅ Администратор <code>{user_id}</code> удалён."

    await state.clear()
    await message.answer(text, reply_markup=admin_manage_keyboard())


@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    try:
        total = await count_all_users()
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
    except Exception:
        logger.exception("Error in admin_stats")
        await callback.answer("❌ Ошибка при получении статистики", show_alert=True)


@router.callback_query(F.data == "admin_users_list")
async def admin_users_list(callback: CallbackQuery, bot: Bot):
    try:
        user_ids = await get_all_user_ids()
        if not user_ids:
            await callback.answer("📂 База пуста", show_alert=True)
            return
        ids_text = "\n".join(str(uid) for uid in user_ids)
        file = BufferedInputFile(ids_text.encode("utf-8"), filename="user_ids.txt")
        await callback.message.edit_text(
            f"📋 <b>Список пользователей</b>\n\nВсего: <b>{len(user_ids)}</b>\n\nФайл отправлен ниже ⬇️",
            reply_markup=admin_back_keyboard(),
        )
        await bot.send_document(callback.message.chat.id, file, caption=f"📄 ID пользователей ({len(user_ids)} шт.)")
        await callback.answer()
    except Exception:
        logger.exception("Error in admin_users_list")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "admin_user_info")
async def admin_user_info(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_user_id)
    await callback.message.edit_text(
        "👤 <b>Информация о пользователе</b>\n\nВведите ID пользователя:",
        reply_markup=admin_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_add_vip")
async def admin_add_vip(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_vip_user)
    await callback.message.edit_text(
        "⭐ <b>Добавление VIP</b>\n\nВведите ID пользователя:",
        reply_markup=admin_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_remove_vip")
async def admin_remove_vip(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_remove_vip_user)
    await callback.message.edit_text(
        "❌ <b>Удаление VIP</b>\n\nВведите ID пользователя:",
        reply_markup=admin_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_delete_user")
async def admin_delete_user(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_delete_user)
    await callback.message.edit_text(
        "🗑️ <b>Удаление пользователя</b>\n\n⚠️ <b>ВНИМАНИЕ:</b> Это действие необратимо!\n\nВведите ID пользователя:",
        reply_markup=admin_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_vip_"))
async def admin_set_vip(callback: CallbackQuery, bot: Bot):
    try:
        _, _, plan, user_id = callback.data.split("_")
        user_id = int(user_id)
        await add_or_update_subscription(user_id, plan)
        await callback.message.edit_text(
            f"✅ <b>VIP добавлен</b>\n\nПользователь: <code>{user_id}</code>\nПлан: <b>{plan}</b>",
            reply_markup=admin_back_keyboard(),
        )
        await _notify_user(bot, user_id, "✅ <b>Вам выдали VIP подписку</b>\n\n<i>Теперь вы можете посмотреть кто вам написал!</i>")
        await callback.answer("✅ Готово!")
    except Exception:
        logger.exception("Error in admin_set_vip")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("admin_add_vip_user_"))
async def admin_add_vip_user(callback: CallbackQuery):
    try:
        user_id = int(callback.data.split("_")[-1])
        await callback.message.edit_text(
            f"⭐ <b>Выберите план VIP</b> для пользователя <code>{user_id}</code>:",
            reply_markup=vip_plans_keyboard(user_id),
        )
        await callback.answer()
    except Exception:
        logger.exception("Error in admin_add_vip_user")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("admin_remove_vip_user_"))
async def admin_remove_vip_user(callback: CallbackQuery):
    try:
        user_id = int(callback.data.split("_")[-1])
        await remove_subscription(user_id)
        await callback.message.edit_text(
            f"❌ <b>VIP удалён</b>\n\nПользователь: <code>{user_id}</code>",
            reply_markup=admin_back_keyboard(),
        )
        await callback.answer()
    except Exception:
        logger.exception("Error in admin_remove_vip_user")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("admin_confirm_delete_"))
async def admin_confirm_delete(callback: CallbackQuery):
    try:
        user_id = int(callback.data.split("_")[-1])
        await delete_user_by_id(user_id)
        await callback.message.edit_text(
            f"🗑️ <b>Пользователь удалён</b>\n\nID: <code>{user_id}</code>",
            reply_markup=admin_back_keyboard(),
        )
        await callback.answer()
    except Exception:
        logger.exception("Error in admin_confirm_delete")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "admin_referrals")
async def admin_referrals(callback: CallbackQuery):
    try:
        referrals = await get_all_referral_links()
        await callback.message.edit_text(
            "🔗 <b>Реферальные ссылки</b>\n\nВыберите ссылку или создайте новую:",
            reply_markup=referral_list_keyboard(referrals),
        )
        await callback.answer()
    except Exception:
        logger.exception("Error in admin_referrals")
        await callback.answer("❌ Ошибка", show_alert=True)


async def _render_admin_referral(callback: CallbackQuery, bot: Bot, referral_id: int) -> bool:
    stats = await get_referral_stats(referral_id)
    if not stats:
        await callback.answer("❌ Реферальная ссылка не найдена", show_alert=True)
        return False
    bot_username = (await bot.me()).username
    link = f"https://t.me/{bot_username}?start={referral_payload(stats['code'])}"
    try:
        await callback.message.edit_text(
            format_referral_stats(stats, link),
            reply_markup=referral_stats_keyboard(referral_id, admin=True),
            disable_web_page_preview=True,
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
    return True


@router.callback_query(F.data == "admin_create_referral")
async def admin_create_referral(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_referral_name)
    await callback.message.edit_text(
        "🔗 <b>Создание реферальной ссылки</b>\n\nВведите название кампании:",
        reply_markup=admin_back_keyboard(),
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_referral_name)
async def process_referral_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name or len(name) > 100:
        await message.reply("❌ Название должно содержать от 1 до 100 символов.")
        return
    await state.update_data(referral_name=name)
    await state.set_state(AdminStates.waiting_for_referral_code)
    await message.answer(
        "Введите код ссылки (только латинские буквы, цифры и `_`, до 60 символов).\n"
        "Например: <code>summer_2026</code>",
        reply_markup=admin_back_keyboard(),
    )


@router.message(AdminStates.waiting_for_referral_code)
async def process_referral_code(message: Message, state: FSMContext):
    code = normalize_referral_code(message.text or "")
    if not code:
        await message.reply("❌ Некорректный код. Разрешены только латинские буквы, цифры и `_`.")
        return
    if await get_referral_by_code(code):
        await message.reply("❌ Такой активный реферальный код уже существует.")
        return
    await state.update_data(referral_code=code)
    await state.set_state(AdminStates.waiting_for_referral_price)
    await message.answer(
        "Введите цену за переход числом или `-`, если оплаты за переход нет.",
        reply_markup=admin_back_keyboard(),
    )


@router.message(AdminStates.waiting_for_referral_price)
async def process_referral_price(message: Message, state: FSMContext):
    value = (message.text or "").strip()
    if value == "-":
        price = None
    else:
        try:
            price = float(Decimal(value.replace(",", ".")))
        except (InvalidOperation, ValueError):
            await message.reply("❌ Введите число, например `3.5` или `-`.")
            return
        if price < 0:
            await message.reply("❌ Цена не может быть отрицательной.")
            return
    await state.update_data(referral_price=price)
    await state.set_state(AdminStates.waiting_for_referral_viewer)
    await message.answer(
        "Введите Telegram ID пользователя, которому показывать статистику или `-`.",
        reply_markup=admin_back_keyboard(),
    )


@router.message(AdminStates.waiting_for_referral_viewer)
async def process_referral_viewer(message: Message, state: FSMContext, bot: Bot):
    value = (message.text or "").strip()
    if value == "-":
        viewer_id = None
    elif re.fullmatch(r"\d+", value):
        viewer_id = int(value)
    else:
        await message.reply("❌ Нужен числовой Telegram ID или `-`.")
        return

    data = await state.get_data()
    code = data["referral_code"]
    user = message.from_user
    await add_user_if_not_exists(user.id, user.first_name or "Администратор", user.username, user.last_name)
    try:
        referral = await create_referral_link(
            code=code,
            name=data["referral_name"],
            admin_id=user.id,
            price=data.get("referral_price"),
            viewer_id=viewer_id,
        )
        bot_username = (await bot.me()).username
        link = f"https://t.me/{bot_username}?start={referral_payload(code)}"
        await message.answer(
            "✅ <b>Реферальная ссылка создана</b>\n\n"
            f"Название: <b>{data['referral_name']}</b>\n"
            f"Код: <code>{code}</code>\n"
            f"Цена за переход: <b>{data.get('referral_price') if data.get('referral_price') is not None else '—'}</b>\n"
            f"Viewer ID: <code>{viewer_id}</code>\n\n🔗 <code>{link}</code>",
            reply_markup=admin_back_keyboard(),
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("Failed to create referral link '%s'", code)
        await message.answer("❌ Не удалось создать ссылку. Возможно, код уже занят.", reply_markup=admin_back_keyboard())
    finally:
        await state.clear()


@router.callback_query(F.data.regexp(r"^admin_referral_\d+$"))
async def admin_referral_details(callback: CallbackQuery, bot: Bot):
    referral_id = int(callback.data.rsplit("_", 1)[1])
    await _render_admin_referral(callback, bot, referral_id)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^admin_referral_refresh_\d+$"))
async def admin_referral_refresh(callback: CallbackQuery, bot: Bot):
    referral_id = int(callback.data.rsplit("_", 1)[1])
    if await _render_admin_referral(callback, bot, referral_id):
        await callback.answer("🔄 Статистика обновлена или уже актуальна")


@router.callback_query(F.data == "admin_growth_chart")
async def admin_growth_chart(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer("📊 Генерирую график...")
        growth_data = await get_user_growth_data(days=7)
        chart_buf = await generate_user_growth_chart(growth_data)
        chart_file = BufferedInputFile(chart_buf.getvalue(), filename="user_growth.png")
        await bot.send_photo(callback.message.chat.id, chart_file, caption="📊 <b>График роста пользователей за неделю</b>")
        user_ids = await get_all_user_ids()
        ids_text = "\n".join(str(uid) for uid in user_ids)
        file = BufferedInputFile(ids_text.encode("utf-8"), filename="user_ids.txt")
        await bot.send_document(callback.message.chat.id, file, caption=f"📄 Список ID ({len(user_ids)} шт.)")
        await callback.message.answer("📊 <b>Статистика</b>\n\nВыберите действие:", reply_markup=admin_stats_keyboard())
    except Exception:
        logger.exception("Error in admin_growth_chart")
        await callback.answer("❌ Ошибка при генерации графика", show_alert=True)


@router.callback_query(F.data == "admin_messages_chart")
async def admin_messages_chart(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer("📈 Генерирую график...")
        messages_data = await get_message_count_data(days=7)
        chart_buf = await generate_message_count_chart(messages_data)
        chart_file = BufferedInputFile(chart_buf.getvalue(), filename="messages.png")
        await bot.send_photo(callback.message.chat.id, chart_file, caption="📈 <b>График отправленных сообщений за неделю</b>")
        await callback.message.answer("📊 <b>Статистика</b>\n\nВыберите действие:", reply_markup=admin_stats_keyboard())
    except Exception:
        logger.exception("Error in messages chart")
        await callback.answer("❌ Ошибка", show_alert=True)


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
        f"👤 <b>Информация</b>\n\nID: <code>{user_id}</code>\n"
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
        reply_markup=vip_plans_keyboard(user_id),
    )
    await state.clear()


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
