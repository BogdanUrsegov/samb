# bot/database/session.py
import logging
import os

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .admins import ensure_superadmin
from .models import Base

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/database.db")

# SQLite has a single writer. Keep one pooled connection in this process so
# concurrent async handlers cannot create competing SQLite write transactions.
# A generous SQLite timeout remains important for startup / external processes.
_engine_kwargs = {"echo": False, "pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs.update(
        pool_size=1,
        max_overflow=0,
        pool_timeout=30,
        connect_args={"timeout": 30},
    )

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Configure every SQLite connection for concurrent bot workloads."""
    if not DATABASE_URL.startswith("sqlite"):
        return

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create tables and initialize the database safely."""
    try:
        async with engine.begin() as conn:
            if DATABASE_URL.startswith("sqlite"):
                await conn.execute(text("PRAGMA journal_mode=WAL"))
                await conn.execute(text("PRAGMA synchronous=NORMAL"))
                await conn.execute(text("PRAGMA busy_timeout=30000"))
                await conn.execute(text("PRAGMA foreign_keys=ON"))
            await conn.run_sync(Base.metadata.create_all)

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
        logger.exception("Ошибка при инициализации БД: %s", e)
        raise
