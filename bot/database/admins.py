"""Database helpers for bot administrators."""

import logging
from typing import Optional

from sqlalchemy import delete, select

from .models import Admin
from .session import async_session

logger = logging.getLogger(__name__)


async def is_admin(user_id: int) -> bool:
    async with async_session() as session:
        result = await session.execute(select(Admin.user_id).where(Admin.user_id == user_id))
        return result.scalar_one_or_none() is not None


async def is_superadmin(user_id: int) -> bool:
    async with async_session() as session:
        result = await session.execute(
            select(Admin.is_superadmin).where(Admin.user_id == user_id)
        )
        return bool(result.scalar_one_or_none())


async def get_admins() -> list[dict]:
    async with async_session() as session:
        result = await session.execute(select(Admin).order_by(Admin.is_superadmin.desc(), Admin.added_at))
        return [
            {
                "user_id": admin.user_id,
                "added_at": admin.added_at,
                "added_by": admin.added_by,
                "is_superadmin": admin.is_superadmin,
            }
            for admin in result.scalars().all()
        ]


async def add_admin(user_id: int, added_by: int, is_superadmin_flag: bool = False) -> bool:
    async with async_session() as session:
        async with session.begin():
            existing = await session.get(Admin, user_id)
            if existing:
                return False
            session.add(Admin(
                user_id=user_id,
                added_by=added_by,
                is_superadmin=is_superadmin_flag,
            ))
            logger.info("Добавлен администратор %s пользователем %s", user_id, added_by)
            return True


async def remove_admin(user_id: int) -> bool:
    async with async_session() as session:
        async with session.begin():
            result = await session.execute(delete(Admin).where(Admin.user_id == user_id))
            removed = result.rowcount > 0
            if removed:
                logger.info("Удалён администратор %s", user_id)
            return removed


async def ensure_superadmin(user_id: Optional[int]) -> None:
    """Seeds ADMIN_ID from .env into the database on every startup."""
    if not user_id:
        return

    async with async_session() as session:
        async with session.begin():
            admin = await session.get(Admin, user_id)
            if admin is None:
                session.add(Admin(user_id=user_id, added_by=None, is_superadmin=True))
                logger.info("Главный администратор %s добавлен в таблицу admins", user_id)
            elif not admin.is_superadmin:
                admin.is_superadmin = True
                admin.added_by = None
                logger.info("Администратор %s повышен до главного администратора из ADMIN_ID", user_id)
