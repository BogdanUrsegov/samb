"""Admin UI for creating and inspecting referral links."""

import logging
import re
from decimal import Decimal, InvalidOperation

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.formatting import html_decoration

from bot.admin.keyboards import admin_back_keyboard, referral_list_keyboard
from bot.admin.states import AdminStates
from bot.create_bot import ADMIN_ID
from bot.database.utils import (
    add_user_if_not_exists,
    create_referral_link,
    get_all_referral_links,
    get_referral_by_code,
    get_referral_stats,
)
from bot.utils.referrals import normalize_referral_code, referral_payload

logger = logging.getLogger(__name__)
router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id == int(ADMIN_ID)


async def _deny(callback: CallbackQuery) -> bool:
    if _is_admin(callback.from_user.id):
        return False
    await callback.answer("❌ Нет доступа", show_alert=True)
    return True


@router.callback_query(F.data == "admin_create_referral")
async def admin_create_referral(callback: CallbackQuery, state: FSMContext):
    if await _deny(callback):
        return
    await state.set_state(AdminStates.waiting_for_referral_name)
    await callback.message.edit_text(
        "🔗 <b>Создание реферальной ссылки</b>\n\n"
        "Введите название кампании:",
        reply_markup=admin_back_keyboard(),
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_referral_name)
async def process_referral_name(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    name = (message.text or "").strip()
    if not name or len(name) > 100:
        await message.reply("❌ Название должно содержать от 1 до 100 символов.")
        return
    await state.update_data(referral_name=name)
    await state.set_state(AdminStates.waiting_for_referral_code)
    await message.answer(
        "Введите код ссылки (латиница, цифры, `_` или `-`, до 60 символов).\n"
        "Например: <code>summer_2026</code>",
        reply_markup=admin_back_keyboard(),
    )


@router.message(AdminStates.waiting_for_referral_code)
async def process_referral_code(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    code = normalize_referral_code(message.text or "")
    if not code:
        await message.reply("❌ Некорректный код. Используйте латиницу, цифры, `_` и `-`.")
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
    if not _is_admin(message.from_user.id):
        return
    value = (message.text or "").strip()
    if value == "-":
        price = None
    else:
        try:
            price = float(Decimal(value.replace(",", ".")))
        except (InvalidOperation, ValueError):
            await message.reply("❌ Введите число, например `25.50`, или `-`.")
            return
        if price < 0:
            await message.reply("❌ Цена не может быть отрицательной.")
            return
    await state.update_data(referral_price=price)
    await state.set_state(AdminStates.waiting_for_referral_viewer)
    await message.answer(
        "Введите Telegram ID пользователя, которому показывать статистику, или `-`.",
        reply_markup=admin_back_keyboard(),
    )


@router.message(AdminStates.waiting_for_referral_viewer)
async def process_referral_viewer(message: Message, state: FSMContext, bot: Bot):
    if not _is_admin(message.from_user.id):
        return
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

    # created_by has an FK to users, so make sure the admin exists in the DB.
    user = message.from_user
    await add_user_if_not_exists(
        user.id,
        user.first_name or "Администратор",
        user.username,
        user.last_name,
    )

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
            f"Название: <b>{html_decoration.quote(data['referral_name'])}</b>\n"
            f"Код: <code>{code}</code>\n"
            f"Цена за переход: <b>{data.get('referral_price') if data.get('referral_price') is not None else '—'}</b>\n"
            f"Viewer ID: <code>{viewer_id}</code>\n\n"
            f"🔗 <code>{link}</code>",
            reply_markup=admin_back_keyboard(),
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("Failed to create referral link '%s'", code)
        await message.answer("❌ Не удалось создать ссылку. Возможно, код уже занят.", reply_markup=admin_back_keyboard())
    finally:
        await state.clear()


@router.callback_query(F.data.startswith("admin_referral_"))
async def admin_referral_details(callback: CallbackQuery, bot: Bot):
    if await _deny(callback):
        return
    try:
        referral_id = int(callback.data.rsplit("_", 1)[1])
    except (ValueError, IndexError):
        return await callback.answer("❌ Некорректная ссылка", show_alert=True)

    stats = await get_referral_stats(referral_id)
    if not stats:
        return await callback.answer("❌ Реферальная ссылка не найдена", show_alert=True)

    bot_username = (await bot.me()).username
    link = f"https://t.me/{bot_username}?start={referral_payload(stats['code'])}"
    recent_lines = []
    for click in stats.get("recent_clicks", []):
        username = f"@{click['username']}" if click.get("username") else "без username"
        recent_lines.append(
            f"• <code>{click['user_id']}</code> — {html_decoration.quote(click.get('first_name') or 'Пользователь')} ({username})"
        )

    text = (
        "🔗 <b>Реферальная ссылка</b>\n\n"
        f"Название: <b>{html_decoration.quote(stats['name'])}</b>\n"
        f"Код: <code>{stats['code']}</code>\n"
        f"Переходов: <b>{stats['total_clicks']}</b>\n"
        f"Цена: <b>{stats['price'] if stats.get('price') is not None else '—'}</b>\n"
        f"Сумма: <b>{stats['total_amount'] if stats.get('total_amount') is not None else '—'}</b>\n"
        f"Viewer ID: <code>{stats.get('viewer_id') or '—'}</code>\n\n"
        f"🔗 <code>{link}</code>\n\n"
        "<b>Последние переходы:</b>\n"
        + ("\n".join(recent_lines) if recent_lines else "— пока нет переходов")
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_back_keyboard(),
        disable_web_page_preview=True,
    )
    await callback.answer()
