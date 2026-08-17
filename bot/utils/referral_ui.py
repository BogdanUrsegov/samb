"""Shared UI helpers for referral statistics."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.formatting import html_decoration


def referral_stats_keyboard(referral_id: int, *, admin: bool = False) -> InlineKeyboardMarkup:
    """Build the referral statistics actions for an admin or assigned viewer."""

    buttons = []
    if admin:
        buttons.append([
            InlineKeyboardButton(text="◀️ К списку", callback_data="admin_referrals")
        ])
        buttons.append([
            InlineKeyboardButton(text="🔄 Обновить", callback_data=f"admin_referral_refresh_{referral_id}")
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def format_referral_stats(stats: dict, link: str) -> str:
    """Render one canonical referral statistics screen for both admin and viewer."""
    recent_lines = []
    for click in stats.get("recent_clicks", []):
        username = f"@{click['username']}" if click.get("username") else "без username"
        recent_lines.append(
            f"• <code>{click['user_id']}</code> — "
            f"{html_decoration.quote(click.get('first_name') or 'Пользователь')} ({username})"
        )

    return (
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
