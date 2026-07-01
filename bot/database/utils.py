"""
Функции для работы с базой данных SQLite (SQLAlchemy 2.0 async).
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from .models import User, Message, Subscription, ReferralLink, ReferralClick

from sqlalchemy import (
    select, update, delete, func, text, and_, or_
)

from .session import async_session

logger = logging.getLogger(__name__)

# ─── Users ───────────────────────────────────────────────────────────────────

async def add_user_if_not_exists(
    user_id: int,
    first_name: str,
    username: Optional[str] = None,
    last_name: Optional[str] = None,
) -> bool:
    """Добавляет/обновляет пользователя. Возвращает True если новый."""
    is_new_user = False
    try:
        async with async_session() as session:
            async with session.begin():
                result = await session.execute(select(User).where(User.user_id == user_id))
                existing = result.scalar_one_or_none()

                if existing is None:
                    new_user = User(
                        user_id=user_id, username=username,
                        first_name=first_name, last_name=last_name
                    )
                    session.add(new_user)
                    is_new_user = True
                    logger.info(f"Добавлен новый пользователь {user_id} (@{username}, {first_name})")
                else:
                    existing.username = username or existing.username
                    existing.first_name = first_name or existing.first_name
                    existing.last_name = last_name or existing.last_name
                    existing.last_activity = datetime.utcnow()
                    logger.debug(f"Обновлён пользователь {user_id}")

        return is_new_user
    except Exception as e:
        logger.exception(f"Ошибка при добавлении/обновлении пользователя {user_id}: {e}")
        raise


async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    try:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.user_id == user_id))
            user = result.scalar_one_or_none()
            if user:
                return {c.name: getattr(user, c.name) for c in user.__table__.columns}
            return None
    except Exception as e:
        logger.exception(f"Ошибка при получении пользователя {user_id}: {e}")
        raise


async def get_user_stats(user_id: int) -> Optional[Dict[str, Any]]:
    try:
        async with async_session() as session:
            stmt = select(
                User.user_id, User.username, User.first_name, User.last_name,
                User.messages_received, User.messages_sent, User.link_clicks,
                User.custom_start_param
            ).where(User.user_id == user_id)
            result = await session.execute(stmt)
            row = result.one_or_none()
            return dict(row._mapping) if row else None
    except Exception as e:
        logger.exception(f"Ошибка при получении статистики {user_id}: {e}")
        raise


async def increment_link_clicks(user_id: int) -> None:
    try:
        async with async_session() as session:
            async with session.begin():
                await session.execute(
                    update(User).where(User.user_id == user_id)
                    .values(link_clicks=User.link_clicks + 1)
                )
                result = await session.execute(
                    select(User.first_name, User.username, User.custom_start_param)
                    .where(User.user_id == user_id)
                )
                row = result.one_or_none()
                if row:
                    logger.info(f"Клик по ссылке: user {user_id}, param {row[2]}")
    except Exception as e:
        logger.exception(f"Ошибка increment_link_clicks {user_id}: {e}")
        raise


async def get_user_id_by_custom_start_param(custom_param: str) -> Optional[int]:
    try:
        async with async_session() as session:
            result = await session.execute(
                select(User.user_id).where(User.custom_start_param == custom_param)
            )
            return result.scalar_one_or_none()
    except Exception as e:
        logger.exception(f"Ошибка поиска по параметру '{custom_param}': {e}")
        raise


async def check_custom_start_param_exists(custom_param: str) -> bool:
    try:
        async with async_session() as session:
            result = await session.execute(
                select(text("1")).where(User.custom_start_param == custom_param).limit(1)
            )
            return result.first() is not None
    except Exception as e:
        logger.exception(f"Ошибка проверки параметра '{custom_param}': {e}")
        raise


async def set_custom_start_param(user_id: int, custom_param: str) -> None:
    try:
        async with async_session() as session:
            async with session.begin():
                await session.execute(
                    update(User).where(User.user_id == user_id)
                    .values(custom_start_param=custom_param)
                )
                result = await session.execute(select(User).where(User.user_id == user_id))
                user = result.scalar_one_or_none()
                if user:
                    logger.info(f"Установлен кастомный параметр '{custom_param}' для user {user_id}")
    except Exception as e:
        logger.exception(f"Ошибка установки параметра '{custom_param}' для {user_id}: {e}")
        raise


# ─── Messages ────────────────────────────────────────────────────────────────

async def add_message_link(
    recipient_id: int, received_message_id: int,
    sender_id: int, sender_message_id: int,
    sender_first_name: str, sender_username: Optional[str] = None,
) -> None:
    try:
        async with async_session() as session:
            async with session.begin():
                session.add(Message(
                    recipient_id=recipient_id, received_message_id=received_message_id,
                    sender_id=sender_id, sender_message_id=sender_message_id,
                    sender_first_name=sender_first_name, sender_username=sender_username,
                ))
                logger.debug(f"Добавлена связь сообщений: {sender_id} -> {recipient_id}")
    except Exception as e:
        logger.exception(f"Ошибка добавления связи сообщений: {e}")
        raise


async def get_sender_info_by_message(
    recipient_id: int, received_message_id: int
) -> Optional[Dict[str, Any]]:
    try:
        async with async_session() as session:
            stmt = select(
                Message.sender_id, Message.sender_message_id,
                Message.sender_first_name, Message.sender_username
            ).where(
                and_(Message.recipient_id == recipient_id,
                     Message.received_message_id == received_message_id)
            ).order_by(Message.id.desc()).limit(1)
            result = await session.execute(stmt)
            row = result.one_or_none()
            return dict(row._mapping) if row else None
    except Exception as e:
        logger.exception(f"Ошибка get_sender_info_by_message: {e}")
        raise


async def increment_received_count(user_id: int) -> None:
    try:
        async with async_session() as session:
            async with session.begin():
                await session.execute(
                    update(User).where(User.user_id == user_id)
                    .values(messages_received=User.messages_received + 1)
                )
                logger.debug(f"Увеличен счётчик полученных сообщений для user {user_id}")
    except Exception as e:
        logger.exception(f"Ошибка increment_received_count {user_id}: {e}")
        raise


async def increment_sent_count(user_id: int) -> None:
    try:
        async with async_session() as session:
            async with session.begin():
                await session.execute(
                    update(User).where(User.user_id == user_id)
                    .values(messages_sent=User.messages_sent + 1)
                )
                logger.debug(f"Увеличен счётчик отправленных сообщений для user {user_id}")
    except Exception as e:
        logger.exception(f"Ошибка increment_sent_count {user_id}: {e}")
        raise


# ─── Subscriptions ───────────────────────────────────────────────────────────

async def get_subscription(user_id: int) -> Optional[Dict[str, Any]]:
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.user_id == user_id)
            )
            sub = result.scalar_one_or_none()
            if not sub:
                return None

            data = {c.name: getattr(sub, c.name) for c in sub.__table__.columns}

            if data["plan"] != "forever" and data["expiry_date"]:
                if data["expiry_date"] < datetime.now():
                    data["is_active"] = False
                    if sub.is_active:
                        logger.info(f"Истекла подписка у user {user_id}, план {data.get('plan')}")
            return data
    except Exception as e:
        logger.exception(f"Ошибка get_subscription {user_id}: {e}")
        raise


async def add_or_update_subscription(user_id: int, plan: str) -> None:
    try:
        start_date = datetime.now()
        expiry_date = None
        if plan == "weekly":
            expiry_date = start_date + timedelta(days=7)
        elif plan == "monthly":
            expiry_date = start_date + timedelta(days=30)

        async with async_session() as session:
            async with session.begin():
                result = await session.execute(
                    select(Subscription).where(Subscription.user_id == user_id)
                )
                existing = result.scalar_one_or_none()

                if existing:
                    existing.is_active = True
                    existing.plan = plan
                    existing.start_date = start_date
                    existing.expiry_date = expiry_date
                    logger.info(f"Обновлена подписка user {user_id} на план {plan}")
                else:
                    session.add(Subscription(
                        user_id=user_id, is_active=True,
                        plan=plan, start_date=start_date, expiry_date=expiry_date
                    ))
                    logger.info(f"Добавлена подписка user {user_id} на план {plan}")
    except Exception as e:
        logger.exception(f"Ошибка add_or_update_subscription {user_id}: {e}")
        raise


async def remove_subscription(user_id: int) -> bool:
    try:
        async with async_session() as session:
            async with session.begin():
                result = await session.execute(
                    delete(Subscription).where(Subscription.user_id == user_id)
                )
                if result.rowcount > 0:
                    logger.info(f"Удалена подписка user {user_id}")
                return result.rowcount > 0
    except Exception as e:
        logger.exception(f"Ошибка remove_subscription {user_id}: {e}")
        raise


async def get_subscription_plans() -> Dict[str, int]:
    try:
        async with async_session() as session:
            stmt = select(
                Subscription.plan, func.count().label("count")
            ).where(
                and_(
                    Subscription.is_active == True,
                    or_(Subscription.plan == "forever", Subscription.expiry_date >= text("CURRENT_TIMESTAMP"))
                )
            ).group_by(Subscription.plan)
            result = await session.execute(stmt)
            rows = result.all()
            data = {"weekly": 0, "monthly": 0, "forever": 0}
            for plan, count in rows:
                if plan in data:
                    data[plan] = count
            return data
    except Exception as e:
        logger.exception(f"Ошибка get_subscription_plans: {e}")
        raise


# ─── Stats ───────────────────────────────────────────────────────────────────

async def get_all_user_ids() -> list[int]:
    async with async_session() as session:
        result = await session.execute(select(User.user_id).order_by(User.user_id))
        return [row[0] for row in result.all()]


async def count_all_users() -> int:
    async with async_session() as session:
        result = await session.execute(select(func.count()).select_from(User))
        return result.scalar() or 0


async def get_user_growth_data(days: int = 7) -> Dict[str, int]:
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        result: Dict[str, int] = {}
        current = start_date
        while current <= end_date:
            result[current.strftime("%Y-%m-%d")] = 0
            current += timedelta(days=1)

        async with async_session() as session:
            stmt = select(
                func.date(User.registration_date).label("date"),
                func.count().label("count")
            ).where(User.registration_date >= start_date.strftime("%Y-%m-%d")
            ).group_by(text("date")).order_by(text("date"))
            rows = (await session.execute(stmt)).all()
            for row in rows:
                if row.date in result:
                    result[row.date] = row.count
        return result
    except Exception as e:
        logger.exception(f"Ошибка get_user_growth_data: {e}")
        raise


async def get_message_count_data(days: int = 7) -> Dict[str, int]:
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        result: Dict[str, int] = {}
        current = start_date
        while current <= end_date:
            result[current.strftime("%Y-%m-%d")] = 0
            current += timedelta(days=1)

        async with async_session() as session:
            stmt = select(
                func.date(Message.sent_date).label("date"),
                func.count().label("count")
            ).where(Message.sent_date >= start_date.strftime("%Y-%m-%d")
            ).group_by(text("date")).order_by(text("date"))
            rows = (await session.execute(stmt)).all()
            for row in rows:
                if row.date in result:
                    result[row.date] = row.count
        return result
    except Exception as e:
        logger.exception(f"Ошибка get_message_count_data: {e}")
        raise


async def delete_user_by_id(user_id: int) -> bool:
    try:
        async with async_session() as session:
            async with session.begin():
                await session.execute(delete(Subscription).where(Subscription.user_id == user_id))
                await session.execute(delete(Message).where(
                    or_(Message.recipient_id == user_id, Message.sender_id == user_id)
                ))
                await session.execute(delete(ReferralClick).where(ReferralClick.user_id == user_id))
                subq = select(ReferralLink.id).where(ReferralLink.created_by == user_id)
                await session.execute(delete(ReferralClick).where(ReferralClick.referral_id.in_(subq)))
                await session.execute(delete(ReferralLink).where(ReferralLink.created_by == user_id))
                result = await session.execute(delete(User).where(User.user_id == user_id))
                if result.rowcount > 0:
                    logger.info(f"Удалён пользователь {user_id}")
                return result.rowcount > 0
    except Exception as e:
        logger.exception(f"Ошибка delete_user_by_id {user_id}: {e}")
        raise


# ─── Referrals ───────────────────────────────────────────────────────────────

async def create_referral_link(
    code: str, name: str, admin_id: int,
    price: Optional[float] = None, viewer_id: Optional[int] = None,
) -> dict:
    try:
        if isinstance(price, str) and price.strip() == "-":
            price = None
        if isinstance(viewer_id, str):
            viewer_id = int(viewer_id) if viewer_id.strip().isdigit() and viewer_id.strip() != "-" else None

        async with async_session() as session:
            async with session.begin():
                link = ReferralLink(
                    code=code, name=name, created_by=admin_id,
                    price=price, viewer_id=viewer_id
                )
                session.add(link)
                await session.flush()
                data = {c.name: getattr(link, c.name) for c in link.__table__.columns}
                logger.info(f"Создана реферальная ссылка '{name}' ({code}) админом {admin_id}")
                return data
    except Exception as e:
        logger.exception(f"Ошибка create_referral_link '{code}': {e}")
        raise


async def get_referral_by_code(code: str) -> Optional[Dict[str, Any]]:
    try:
        async with async_session() as session:
            result = await session.execute(
                select(ReferralLink).where(
                    and_(ReferralLink.code == code, ReferralLink.is_active == True)
                )
            )
            link = result.scalar_one_or_none()
            return {c.name: getattr(link, c.name) for c in link.__table__.columns} if link else None
    except Exception as e:
        logger.exception(f"Ошибка get_referral_by_code '{code}': {e}")
        raise


async def record_referral_click(referral_id: int, user_id: int) -> bool:
    try:
        async with async_session() as session:
            async with session.begin():
                exists = await session.execute(
                    select(text("1")).where(
                        and_(ReferralClick.referral_id == referral_id, ReferralClick.user_id == user_id)
                    ).limit(1)
                )
                if exists.first():
                    return True

                user = await session.execute(select(User).where(User.user_id == user_id))
                if not user.scalar_one_or_none():
                    logger.error(f"Пользователь {user_id} не найден")
                    return False

                session.add(ReferralClick(referral_id=referral_id, user_id=user_id))
                logger.info(f"Записан клик: user {user_id}, ref {referral_id}")
                return True
    except Exception as e:
        logger.exception(f"Ошибка record_referral_click: {e}")
        return False


async def get_all_referral_links() -> List[Dict[str, Any]]:
    try:
        async with async_session() as session:
            stmt = select(
                ReferralLink, func.count(ReferralClick.id).label("clicks")
            ).outerjoin(
                ReferralClick, ReferralLink.id == ReferralClick.referral_id
            ).where(ReferralLink.is_active == True
            ).group_by(ReferralLink.id).order_by(ReferralLink.created_at.desc())
            rows = (await session.execute(stmt)).all()
            result = []
            for link, clicks in rows:
                d = {c.name: getattr(link, c.name) for c in link.__table__.columns}
                d["clicks"] = clicks
                result.append(d)
            return result
    except Exception as e:
        logger.exception(f"Ошибка get_all_referral_links: {e}")
        raise


async def get_referral_stats(referral_id: int) -> Dict[str, Any]:
    try:
        async with async_session() as session:
            result = await session.execute(
                select(ReferralLink).where(ReferralLink.id == referral_id)
            )
            link = result.scalar_one_or_none()
            if not link:
                return {}

            data = {c.name: getattr(link, c.name) for c in link.__table__.columns}

            clicks_result = await session.execute(
                select(func.count()).select_from(ReferralClick).where(ReferralClick.referral_id == referral_id)
            )
            data["total_clicks"] = clicks_result.scalar() or 0

            if data.get("price") and data["price"] > 0:
                data["total_amount"] = round(data["price"] * data["total_clicks"], 2)
            else:
                data["total_amount"] = None

            recent = await session.execute(
                select(
                    ReferralClick.user_id, ReferralClick.clicked_at,
                    User.username, User.first_name, User.last_name
                ).join(User, ReferralClick.user_id == User.user_id
                ).where(ReferralClick.referral_id == referral_id
                ).order_by(ReferralClick.clicked_at.desc()).limit(5)
            )
            data["recent_clicks"] = [dict(r._mapping) for r in recent.all()]
            return data
    except Exception as e:
        logger.exception(f"Ошибка get_referral_stats {referral_id}: {e}")
        raise


async def check_referral_code_exists(code: str) -> bool:
    try:
        async with async_session() as session:
            result = await session.execute(
                select(text("1")).where(
                    and_(ReferralLink.code == code, ReferralLink.is_active == True)
                ).limit(1)
            )
            return result.first() is not None
    except Exception as e:
        logger.exception(f"Ошибка check_referral_code_exists: {e}")
        return True


async def check_referral_name_exists(name: str) -> bool:
    try:
        async with async_session() as session:
            result = await session.execute(
                select(text("1")).where(
                    and_(ReferralLink.name == name, ReferralLink.is_active == True)
                ).limit(1)
            )
            return result.first() is not None
    except Exception as e:
        logger.exception(f"Ошибка check_referral_name_exists: {e}")
        return True


async def check_referral_exists(code: str, name: str) -> Tuple[bool, bool]:
    try:
        return await check_referral_code_exists(code), await check_referral_name_exists(name)
    except Exception as e:
        logger.exception(f"Ошибка check_referral_exists: {e}")
        return True, True


async def delete_referral_link(referral_id: int) -> bool:
    try:
        async with async_session() as session:
            async with session.begin():
                await session.execute(delete(ReferralClick).where(ReferralClick.referral_id == referral_id))
                result = await session.execute(delete(ReferralLink).where(ReferralLink.id == referral_id))
                if result.rowcount > 0:
                    logger.info(f"Удалена реферальная ссылка {referral_id}")
                return result.rowcount > 0
    except Exception as e:
        logger.exception(f"Ошибка delete_referral_link {referral_id}: {e}")
        return False
    

async def db_error():
    async with async_session() as session:
        await session.execute(text("SELECT * FROM nonexistent_table"))