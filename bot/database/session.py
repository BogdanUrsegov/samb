# bot/database/session.py
import os
from sqlalchemy import event
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from .models import Base
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/database.db")

engine = create_async_engine(DATABASE_URL, echo=False)

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Создаёт таблицы и настраивает PRAGMA."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL;"))
            await conn.execute(text("PRAGMA busy_timeout=5000;"))
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Инициализация БД завершена успешно")
    except Exception as e:
        logger.exception(f"Ошибка при инициализации БД: {e}")
        raise

# engine = create_async_engine(
#     DATABASE_URL,
#     echo=False,
#     connect_args={"check_same_thread": False},
#     pool_pre_ping=True,
# )

# # Фабрика сессий
# AsyncSessionLocal = async_sessionmaker(
#     bind=engine,
#     expire_on_commit=False,
# )

# async def init_db():
#     """Создаёт таблицы, если их нет."""
#     try:
#         async with engine.begin() as conn:
#             await conn.run_sync(Base.metadata.create_all)
#             logger.info(f"Таблицы успешно созданы/обновлены в {DATABASE_URL}")
#     except Exception as e:
#         logger.error(f"Ошибка инициализации БД: {e}")
#         raise