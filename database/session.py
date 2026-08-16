# bot/database/session.py
import os
from sqlalchemy import event
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from .models import Base
from .admins import ensure_superadmin
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/database.db")

# SQLite permits only one writer at a time. Keep a single pooled connection so
# concurrent async handlers cannot open competing write transactions.
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"timeout": 30},
    pool_size=1,
    max_overflow=0,
    pool_timeout=30,
)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Создаёт таблицы и настраивает PRAGMA."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL;"))
            await conn.execute(text("PRAGMA busy_timeout=30000;"))
            await conn.run_sync(Base.metadata.create_all)

        # все проверки админки выполняются через таблицу admins.
        admin_id = os.getenv("ADMIN_ID")
        if admin_id:
            try:
                await ensure_superadmin(int(admin_id))
            except ValueError:
                logger.error("ADMIN_ID должен быть числом: %r", admin_id)
                raise
        else:
            logger.warning("ADMIN_ID не задан — главный администратор не был создан")

        logger.info("Инициализация БД завершена успешно")
    except Exception as e:
        logger.exception(f"Ошибка при инициализации БД: {e}")
        raise
