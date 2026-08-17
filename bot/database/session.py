import logging

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings
from .admins import ensure_superadmin
from .models import Base

logger = logging.getLogger(__name__)

# SQLite has a single writer. WAL allows readers to continue while a write is
# in progress; busy_timeout makes short write bursts wait instead of failing.
engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"timeout": 30},
)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
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
    """Create missing tables and initialize SQLite settings."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA busy_timeout=30000"))
            await conn.run_sync(Base.metadata.create_all)

        await ensure_superadmin(settings.admin_id)
        logger.info("Database initialized successfully")
    except Exception:
        logger.exception("Database initialization failed")
        raise
