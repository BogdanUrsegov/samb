from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.admin.filters import IsAdmin
from bot.database.utils import delete_referral_link, get_referral_stats

router = Router()


def referral_delete_confirm_keyboard(referral_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔴 Да, удалить",
            callback_data=f"admin_ref_del_confirm_{referral_id}",
        )],
        [InlineKeyboardButton(
            text="🟢 Отмена",
            callback_data=f"admin_referral_{referral_id}",
        )],
    ])


@router.callback_query(F.data.regexp(r"^admin_ref_del_\d+$"), IsAdmin())
async def admin_referral_delete_start(callback: CallbackQuery):
    referral_id = int(callback.data.rsplit("_", 1)[1])
    stats = await get_referral_stats(referral_id)
    if not stats:
        await callback.answer("❌ Реферальная ссылка не найдена", show_alert=True)
        return

    await callback.message.edit_text(
        "🗑️ <b>Удаление реферальной ссылки</b>\n\n"
        f"Название: <b>{stats['name']}</b>\n"
        f"Код: <code>{stats['code']}</code>\n"
        f"Переходов: <b>{stats['total_clicks']}</b>\n\n"
        "⚠️ <b>Внимание:</b> ссылка и вся статистика переходов по ней будут удалены без возможности восстановления.\n\n"
        "Продолжить?",
        reply_markup=referral_delete_confirm_keyboard(referral_id),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^admin_ref_del_confirm_\d+$"), IsAdmin())
async def admin_referral_delete_confirm(callback: CallbackQuery):
    referral_id = int(callback.data.rsplit("_", 1)[1])
    deleted = await delete_referral_link(referral_id)

    if not deleted:
        await callback.answer("❌ Реферальная ссылка не найдена", show_alert=True)
        return

    await callback.message.edit_text(
        "✅ <b>Реферальная ссылка удалена</b>\n\n"
        "Ссылка и связанная с ней статистика переходов удалены.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 К реферальным ссылкам", callback_data="admin_referrals")],
            [InlineKeyboardButton(text="◀️ В админ-панель", callback_data="admin_back")],
        ]),
    )
    await callback.answer("✅ Ссылка удалена")
